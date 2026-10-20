"""JMP 교차검증 결과 회귀 테스트.

JMP 결과(jmp_dump.csv)가 저장소에 있으면, 현재 코드의 Python 값이
JMP 값과 여전히 일치하는지 확인한다. 코드 수정으로 통계 결과가 바뀌면 여기서 걸린다.
"""
from pathlib import Path

import pandas as pd
import pytest

RESULTS = Path(__file__).resolve().parents[1] / "tools/jmp_crosscheck/results"


@pytest.mark.skipif(not (RESULTS / "jmp_dump.csv").exists(), reason="JMP 결과 없음")
def test_python_matches_jmp(tmp_path, monkeypatch):
    from tools.jmp_crosscheck import compare, python_reference

    python_reference.main()
    compare.main()
    table = pd.read_csv(RESULTS / "crosscheck_table.csv", encoding="utf-8-sig")

    assert len(table) > 100
    mismatched = table[~table["verdict"].str.startswith("일치")]
    assert mismatched.empty, mismatched[["key", "python", "jmp", "verdict"]].to_string()
    assert table["rel_diff"].max() < 1e-3
