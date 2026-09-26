"""모델 패키지 입출력과 호환 처리.

저장 형식이 바뀌었다.

이전: {"model", "features", "classes"} + 라벨이 문자열("Normal"/"Delamination")
현재: {"model", "features", "positive_label", "decision_threshold", ...}
      + 라벨이 정수 0/1

문제가 되는 지점
---------------
predict_proba 의 열 순서는 model.classes_ 순서를 따른다.
문자열 라벨이면 사전순으로 정렬되어 ["Delamination", "Normal"] 이 되므로
predict_proba[:, 1] 은 '정상' 확률이다. 정수 라벨이면 [0, 1] 이므로
predict_proba[:, 1] 이 '불량' 확률이다.

열 번호를 고정하면 옛 모델 파일에서 확률이 정반대로 나온다.
그래서 항상 classes_ 를 보고 불량 클래스의 열을 찾는다.
"""

from pathlib import Path
from typing import Any

import joblib
import numpy as np


DEFAULT_POSITIVE_LABEL = "Delamination"
DEFAULT_THRESHOLD = 0.5


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_model_path() -> Path:
    return (
        get_project_root()
        / "models"
        / "random_forest_defect_model.joblib"
    )


def load_model_package() -> dict[str, Any]:
    """모델 패키지를 읽는다."""
    model_path = get_model_path()

    if not model_path.exists():
        raise FileNotFoundError(
            "학습된 모델이 없습니다. 아래 명령을 먼저 실행하세요.\n"
            "python -m src.ml.train_model\n"
            f"(기대 경로: {model_path})"
        )

    return joblib.load(model_path)


def resolve_positive_index(
    model: Any,
    positive_label: str = DEFAULT_POSITIVE_LABEL,
) -> int:
    """predict_proba 에서 불량 클래스에 해당하는 열 번호를 찾는다."""
    classes = list(getattr(model, "classes_", []))

    if not classes:
        return 1

    # 현재 형식: 정수 0/1 라벨
    if 1 in classes:
        return classes.index(1)

    # 이전 형식: 문자열 라벨
    if positive_label in classes:
        return classes.index(positive_label)

    # 정상으로 보이는 라벨을 제외한 나머지를 불량으로 본다.
    for index, label in enumerate(classes):
        if str(label).lower() not in {"normal", "0", "ok", "pass"}:
            return index

    return len(classes) - 1


def defect_probability(
    model: Any,
    features: Any,
    positive_label: str = DEFAULT_POSITIVE_LABEL,
) -> np.ndarray:
    """불량 확률을 반환한다. 저장 형식에 상관없이 올바른 열을 고른다."""
    index = resolve_positive_index(model, positive_label)

    return np.asarray(model.predict_proba(features))[:, index]


def is_legacy_package(package: dict[str, Any]) -> bool:
    """이전 형식으로 저장된 모델인지 판정한다.

    이전 모델은 판정 임계값이 없어 0.5 가 쓰인다. 불량이 희소한 공정에서
    0.5 는 검출을 거의 포기하는 임계값이므로 화면에서 경고해야 한다.
    """
    return "decision_threshold" not in package


def get_threshold(package: dict[str, Any]) -> float:
    """저장된 판정 임계값을 반환한다. 없으면 0.5."""
    return float(
        package.get("decision_threshold", DEFAULT_THRESHOLD)
    )


def get_positive_label(package: dict[str, Any]) -> str:
    """불량 클래스 이름을 반환한다."""
    return str(
        package.get("positive_label", DEFAULT_POSITIVE_LABEL)
    )
