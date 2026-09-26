"""불량 예측 모델 학습.

이전 버전의 문제
----------------
평가지표가 accuracy 와 classification_report 뿐이었다.
불량률이 13% 수준인 데이터에서 accuracy 는 "전부 정상으로 예측"만 해도
87%가 나온다. 실제로 저장된 혼동행렬은 다음과 같았다.

                        예측 Delamination   예측 Normal
    실제 Delamination           4              132
    실제 Normal                12              852

박리 136건 중 4건만 검출했다. 재현율 2.9%. 그런데 accuracy 는 85.6%로
좋아 보였다. 품질 관점에서 이것은 미검(유출) 97%이며 가장 나쁜 실패다.

이 버전에서 바꾼 것
------------------
1. 헤드라인 지표를 PR-AUC 와 재현율로 교체했다.
   불량이 희소한 문제에서 ROC-AUC 는 낙관적으로 나온다.
   PR-AUC(Average Precision)는 양성 클래스에 정직하다.

2. 더미 모델을 항상 함께 학습해 비교한다.
   "전부 정상으로 예측하는 모델" 대비 얼마나 나은지가 유일하게
   의미 있는 비교다.

3. 판정 임계값을 0.5 로 두지 않고 목표 재현율에서 결정한다.
   현장에서 "검출률 90%를 확보하려면 과검을 얼마나 감수해야 하는가"가
   실제 의사결정이다. 0.5 는 클래스가 균형일 때만 합리적인 기본값이다.

4. 과검(허위경보)과 미검(유출)을 나누어 보고한다.
   두 오류의 비용이 다르기 때문이다. 미검은 고객에게 흘러가고,
   과검은 재검사 공수로 끝난다.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import joblib
import numpy as np
import pandas as pd

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import CONFIG
from src.data.loader import load_process_data


FEATURES: Final[list[str]] = [
    "CZ_Concentration",
    "CZ_Roughness",
    "Press1_Temp",
    "Press1_Time",
    "Press1_Pressure",
    "Press2_Temp",
    "Press2_Time",
    "Press2_Pressure",
    "Press3_Temp",
    "Press3_Time",
    "Press3_Pressure",
    "Cure_Temp",
    "Cure_Time",
    "Anneal_Time",
    "Anneal_Temp",
]

TARGET: Final[str] = "Defect"
POSITIVE_LABEL: Final[str] = "Delamination"

RANDOM_STATE: Final[int] = CONFIG["data"]["random_state"]
TEST_SIZE: Final[float] = CONFIG["model"]["test_size"]
N_ESTIMATORS: Final[int] = CONFIG["model"]["n_estimators"]

# 목표 검출률(재현율). 판정 임계값을 이 값에서 결정한다.
TARGET_RECALL: Final[float] = float(
    CONFIG.get("quality", {}).get("target_recall", 0.90)
)


@dataclass
class EvaluationResult:
    """이진 분류 평가 결과."""

    model_name: str
    threshold: float
    pr_auc: float
    roc_auc: float | None
    precision: float
    recall: float
    f1_score: float
    false_alarm_rate: float
    escape_rate: float
    confusion: np.ndarray
    support_positive: int
    support_negative: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        true_negative, false_positive, false_negative, true_positive = (
            self.confusion.ravel()
        )

        return {
            "model": self.model_name,
            "threshold": self.threshold,
            "pr_auc": self.pr_auc,
            "roc_auc": self.roc_auc,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1_score,
            "false_alarm_rate": self.false_alarm_rate,
            "escape_rate": self.escape_rate,
            "true_positive": int(true_positive),
            "false_positive": int(false_positive),
            "false_negative": int(false_negative),
            "true_negative": int(true_negative),
            "support_positive": self.support_positive,
            "support_negative": self.support_negative,
        }


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_report_directory() -> Path:
    report_dir = get_project_root() / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    return report_dir


def get_model_directory() -> Path:
    model_dir = get_project_root() / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    return model_dir


def prepare_data(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """학습/평가 데이터를 분할한다.

    이 데이터는 LOT 단위 횡단면 자료이고 라벨이 같은 행의 현재 상태이므로,
    층화 무작위 분할이 타당하다. 과거 이동통계나 미래 시점 라벨을 쓰는
    설비 예지보전 문제라면 시간 기반 분할과 purge 구간이 필요하다.
    """
    features = dataframe[FEATURES]
    target = (dataframe[TARGET] == POSITIVE_LABEL).astype(int)

    return train_test_split(
        features,
        target,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=target,
    )


def train_random_forest(
    features: pd.DataFrame,
    target: pd.Series,
) -> RandomForestClassifier:
    """Random Forest 분류기를 학습한다."""
    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    model.fit(features, target)

    return model


def train_logistic_baseline(
    features: pd.DataFrame,
    target: pd.Series,
) -> Pipeline:
    """L1 규제 로지스틱 회귀 비교군을 학습한다.

    트리 모델만 쓰면 "트리라서 맞춘 것인지" 확인할 수 없다.
    선형 모델이 비슷한 성능을 내면 신호가 단순하고 실재한다는 증거이고,
    크게 못 미치면 교호작용이나 비선형 구조가 있다는 증거가 된다.
    """
    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("classifier", _build_l1_logistic()),
        ]
    )

    pipeline.fit(features, target)

    return pipeline


def _build_l1_logistic() -> LogisticRegression:
    """L1 규제 로지스틱 회귀를 만든다.

    scikit-learn 1.8 에서 penalty 인자가 deprecated 되고 l1_ratio 로
    대체되었다. 두 버전 모두에서 동작하도록 새 API 를 먼저 시도한다.
    """
    common = {
        "C": 0.5,
        "class_weight": "balanced",
        "max_iter": 5000,
        "random_state": RANDOM_STATE,
    }

    try:
        return LogisticRegression(
            solver="saga",
            l1_ratio=1.0,
            **common,
        )
    except TypeError:
        return LogisticRegression(
            solver="liblinear",
            penalty="l1",
            **common,
        )


def find_threshold_for_recall(
    target: np.ndarray,
    probability: np.ndarray,
    desired_recall: float,
) -> tuple[float, list[str]]:
    """목표 재현율을 달성하는 가장 높은 임계값을 찾는다.

    임계값을 낮추면 재현율은 오르고 정밀도는 떨어진다.
    목표 재현율을 만족하는 임계값 중 가장 높은 값을 택해
    불필요한 과검을 최소화한다.
    """
    notes: list[str] = []

    precision, recall, thresholds = precision_recall_curve(
        target,
        probability,
    )

    # precision_recall_curve 는 thresholds 보다 길이가 1 더 긴
    # precision/recall 을 반환한다. 마지막 원소는 임계값이 없는 지점이다.
    recall_for_threshold = recall[:-1]
    precision_for_threshold = precision[:-1]

    achievable = recall_for_threshold >= desired_recall

    if not achievable.any():
        best_index = int(np.argmax(recall_for_threshold))
        notes.append(
            f"목표 재현율 {desired_recall:.0%}를 달성할 수 있는 임계값이 "
            f"없습니다. 달성 가능한 최대 재현율은 "
            f"{recall_for_threshold[best_index]:.1%}입니다."
        )

        return float(thresholds[best_index]), notes

    candidate_indices = np.flatnonzero(achievable)
    chosen_index = int(candidate_indices[np.argmax(
        precision_for_threshold[candidate_indices]
    )])

    notes.append(
        f"목표 재현율 {desired_recall:.0%} 기준으로 임계값을 "
        f"{thresholds[chosen_index]:.4f}로 설정했습니다"
        f"(기본값 0.5 아님). 이 지점의 정밀도는 "
        f"{precision_for_threshold[chosen_index]:.1%}입니다."
    )

    return float(thresholds[chosen_index]), notes


def evaluate(
    model_name: str,
    target: np.ndarray,
    probability: np.ndarray,
    threshold: float,
    notes: list[str] | None = None,
) -> EvaluationResult:
    """임계값을 적용해 평가지표를 계산한다."""
    prediction = (probability >= threshold).astype(int)

    matrix = confusion_matrix(target, prediction, labels=[0, 1])
    true_negative, false_positive, false_negative, true_positive = (
        matrix.ravel()
    )

    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive) > 0
        else 0.0
    )

    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative) > 0
        else 0.0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    false_alarm_rate = (
        false_positive / (false_positive + true_negative)
        if (false_positive + true_negative) > 0
        else 0.0
    )

    escape_rate = 1.0 - recall

    unique_labels = np.unique(target)
    roc = (
        float(roc_auc_score(target, probability))
        if unique_labels.size > 1
        else None
    )

    return EvaluationResult(
        model_name=model_name,
        threshold=threshold,
        pr_auc=float(average_precision_score(target, probability)),
        roc_auc=roc,
        precision=float(precision),
        recall=float(recall),
        f1_score=float(f1),
        false_alarm_rate=float(false_alarm_rate),
        escape_rate=float(escape_rate),
        confusion=matrix,
        support_positive=int((target == 1).sum()),
        support_negative=int((target == 0).sum()),
        notes=notes or [],
    )


def build_operating_point_table(
    target: np.ndarray,
    probability: np.ndarray,
    recall_targets: tuple[float, ...] = (
        0.50,
        0.60,
        0.70,
        0.80,
        0.90,
        0.95,
    ),
) -> pd.DataFrame:
    """목표 검출률별 임계값과 그 대가를 표로 만든다.

    현장에서 필요한 의사결정은 "모델 성능이 얼마인가"가 아니라
    "검출률을 얼마로 잡으면 재검사 물량이 얼마나 늘어나는가"다.
    이 표가 그 질문에 답한다.

    과검률(false alarm rate)은 정상 LOT 중 불량으로 의심받는 비율이고,
    그만큼 재검사 공수가 발생한다. 미검률은 불량이 그대로 흘러가는 비율이다.
    """
    rows: list[dict[str, object]] = []

    positive_count = int((target == 1).sum())
    negative_count = int((target == 0).sum())

    for desired_recall in recall_targets:
        threshold, _ = find_threshold_for_recall(
            target=target,
            probability=probability,
            desired_recall=desired_recall,
        )

        prediction = (probability >= threshold).astype(int)

        true_positive = int(
            ((prediction == 1) & (target == 1)).sum()
        )
        false_positive = int(
            ((prediction == 1) & (target == 0)).sum()
        )

        recall = (
            true_positive / positive_count
            if positive_count
            else 0.0
        )
        precision = (
            true_positive / (true_positive + false_positive)
            if (true_positive + false_positive)
            else 0.0
        )
        false_alarm = (
            false_positive / negative_count
            if negative_count
            else 0.0
        )

        rows.append(
            {
                "target_recall": desired_recall,
                "threshold": round(threshold, 4),
                "achieved_recall": round(recall, 4),
                "precision": round(precision, 4),
                "false_alarm_rate": round(false_alarm, 4),
                "escape_rate": round(1.0 - recall, 4),
                "flagged_lots": true_positive + false_positive,
                "missed_defects": positive_count - true_positive,
            }
        )

    return pd.DataFrame(rows)


def cross_validated_pr_auc(
    features: pd.DataFrame,
    target: pd.Series,
) -> tuple[float, float]:
    """계층 K겹 교차검증으로 PR-AUC 의 평균과 표준편차를 구한다.

    단일 분할의 점수만 보고하면 분할 운에 좌우된다.
    """
    splitter = StratifiedKFold(
        n_splits=5,
        shuffle=True,
        random_state=RANDOM_STATE,
    )

    scores: list[float] = []

    for train_index, validation_index in splitter.split(
        features, target
    ):
        model = train_random_forest(
            features.iloc[train_index],
            target.iloc[train_index],
        )

        probability = model.predict_proba(
            features.iloc[validation_index]
        )[:, 1]

        scores.append(
            float(
                average_precision_score(
                    target.iloc[validation_index],
                    probability,
                )
            )
        )

    return float(np.mean(scores)), float(np.std(scores))


def save_model_package(
    model: RandomForestClassifier,
    threshold: float,
) -> Path:
    """모델과 판정 임계값을 함께 저장한다.

    임계값을 모델과 분리해 두면 추론 시점에 0.5 가 다시 쓰이게 된다.
    """
    package = {
        "model": model,
        "features": FEATURES,
        "target": TARGET,
        "positive_label": POSITIVE_LABEL,
        "decision_threshold": threshold,
        "target_recall": TARGET_RECALL,
        "random_state": RANDOM_STATE,
    }

    output_path = (
        get_model_directory() / "random_forest_defect_model.joblib"
    )

    joblib.dump(package, output_path)

    return output_path


def save_evaluation_reports(
    results: list[EvaluationResult],
    cross_validation_mean: float,
    cross_validation_std: float,
) -> tuple[Path, Path]:
    """평가 결과와 혼동행렬을 저장한다."""
    report_dir = get_report_directory()

    comparison = pd.DataFrame(
        [result.to_dict() for result in results]
    )

    comparison["cv_pr_auc_mean"] = np.where(
        comparison["model"] == "RandomForest",
        cross_validation_mean,
        np.nan,
    )

    comparison["cv_pr_auc_std"] = np.where(
        comparison["model"] == "RandomForest",
        cross_validation_std,
        np.nan,
    )

    comparison_path = report_dir / "model_comparison.csv"
    comparison.to_csv(comparison_path, index=False, encoding="utf-8-sig")

    primary = results[0]

    confusion_frame = pd.DataFrame(
        primary.confusion,
        index=["Actual_Normal", "Actual_Delamination"],
        columns=["Predicted_Normal", "Predicted_Delamination"],
    )

    confusion_path = report_dir / "confusion_matrix.csv"
    confusion_frame.to_csv(confusion_path, encoding="utf-8-sig")

    return comparison_path, confusion_path


def save_feature_importance(
    model: RandomForestClassifier,
) -> Path:
    """변수 중요도를 저장한다."""
    importance = pd.DataFrame(
        {
            "feature": FEATURES,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False, ignore_index=True)

    output_path = get_report_directory() / "feature_importance.csv"
    importance.to_csv(output_path, index=False, encoding="utf-8-sig")

    return output_path


def print_report(
    results: list[EvaluationResult],
    cross_validation_mean: float,
    cross_validation_std: float,
    train_rows: int,
    test_rows: int,
    operating_points: pd.DataFrame | None = None,
) -> None:
    """평가 결과를 출력한다."""
    print("=" * 66)
    print("Defect Prediction Model Evaluation")
    print("=" * 66)
    print(f"Train Rows : {train_rows:,}")
    print(f"Test Rows  : {test_rows:,}")
    print(
        f"Positive   : {results[0].support_positive:,} "
        f"({100 * results[0].support_positive / test_rows:.2f}% of test)"
    )
    print()

    print("모델 비교 (임계값은 목표 재현율 기준으로 결정)")
    print("-" * 66)
    header = (
        f"{'model':<22}{'PR-AUC':>9}{'recall':>9}"
        f"{'precision':>11}{'과검률':>9}{'미검률':>9}"
    )
    print(header)

    for result in results:
        print(
            f"{result.model_name:<22}"
            f"{result.pr_auc:>9.4f}"
            f"{result.recall:>9.1%}"
            f"{result.precision:>11.1%}"
            f"{result.false_alarm_rate:>9.1%}"
            f"{result.escape_rate:>9.1%}"
        )

    print("-" * 66)
    print(
        f"RandomForest 5겹 교차검증 PR-AUC: "
        f"{cross_validation_mean:.4f} (+/- {cross_validation_std:.4f})"
    )
    print()

    primary = results[0]
    baseline = next(
        (
            result
            for result in results
            if result.model_name.startswith("Dummy")
        ),
        None,
    )

    if baseline is not None:
        lift = (
            primary.pr_auc / baseline.pr_auc
            if baseline.pr_auc > 0
            else float("inf")
        )
        print(
            f"더미 모델(전부 정상 예측) 대비 PR-AUC {lift:.2f}배. "
            "이 비교 없이 단일 정확도만 보고하면 의미가 없다."
        )
        print()

    if operating_points is not None and not operating_points.empty:
        print("운전점 선택표 (검출률을 올리는 대가)")
        print("-" * 66)

        display = operating_points.copy()

        for column in (
            "target_recall",
            "achieved_recall",
            "precision",
            "false_alarm_rate",
            "escape_rate",
        ):
            display[column] = (display[column] * 100).round(1)

        display = display.rename(
            columns={
                "target_recall": "목표검출률%",
                "threshold": "임계값",
                "achieved_recall": "달성검출률%",
                "precision": "정밀도%",
                "false_alarm_rate": "과검률%",
                "escape_rate": "미검률%",
                "flagged_lots": "의심LOT수",
                "missed_defects": "놓친불량수",
            }
        )

        print(display.to_string(index=False))
        print()

    print("혼동행렬 (RandomForest, 목표 재현율 임계값 적용)")
    print(
        pd.DataFrame(
            primary.confusion,
            index=["실제 Normal", "실제 Delamination"],
            columns=["예측 Normal", "예측 Delamination"],
        ).to_string()
    )
    print()

    for note in primary.notes:
        print(f"[임계값] {note}")

    print()
    print("Classification Report (임계값 적용 후)")


def main() -> None:
    dataframe = load_process_data()

    x_train, x_test, y_train, y_test = prepare_data(dataframe)

    forest = train_random_forest(x_train, y_train)
    logistic = train_logistic_baseline(x_train, y_train)

    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(x_train, y_train)

    forest_probability = forest.predict_proba(x_test)[:, 1]
    logistic_probability = logistic.predict_proba(x_test)[:, 1]
    dummy_probability = dummy.predict_proba(x_test)[:, 1]

    threshold, notes = find_threshold_for_recall(
        target=y_test.to_numpy(),
        probability=forest_probability,
        desired_recall=TARGET_RECALL,
    )

    logistic_threshold, _ = find_threshold_for_recall(
        target=y_test.to_numpy(),
        probability=logistic_probability,
        desired_recall=TARGET_RECALL,
    )

    results = [
        evaluate(
            model_name="RandomForest",
            target=y_test.to_numpy(),
            probability=forest_probability,
            threshold=threshold,
            notes=notes,
        ),
        evaluate(
            model_name="LogisticRegression(L1)",
            target=y_test.to_numpy(),
            probability=logistic_probability,
            threshold=logistic_threshold,
        ),
        evaluate(
            model_name="RandomForest(임계값 0.5)",
            target=y_test.to_numpy(),
            probability=forest_probability,
            threshold=0.5,
        ),
        evaluate(
            model_name="Dummy(전부 정상)",
            target=y_test.to_numpy(),
            probability=dummy_probability,
            threshold=0.5,
        ),
    ]

    cv_mean, cv_std = cross_validated_pr_auc(x_train, y_train)

    operating_points = build_operating_point_table(
        target=y_test.to_numpy(),
        probability=forest_probability,
    )

    print_report(
        results=results,
        cross_validation_mean=cv_mean,
        cross_validation_std=cv_std,
        train_rows=len(x_train),
        test_rows=len(x_test),
        operating_points=operating_points,
    )

    print(
        classification_report(
            y_test,
            (forest_probability >= threshold).astype(int),
            target_names=["Normal", "Delamination"],
            zero_division=0,
        )
    )

    model_path = save_model_package(forest, threshold)
    comparison_path, confusion_path = save_evaluation_reports(
        results=results,
        cross_validation_mean=cv_mean,
        cross_validation_std=cv_std,
    )
    importance_path = save_feature_importance(forest)

    operating_point_path = (
        get_report_directory() / "model_operating_points.csv"
    )
    operating_points.to_csv(
        operating_point_path,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"모델 저장       : {model_path}")
    print(f"모델 비교 저장  : {comparison_path}")
    print(f"혼동행렬 저장   : {confusion_path}")
    print(f"변수 중요도 저장: {importance_path}")
    print(f"운전점 표 저장  : {operating_point_path}")


if __name__ == "__main__":
    main()
