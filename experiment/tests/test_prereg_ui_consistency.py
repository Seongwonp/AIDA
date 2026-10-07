"""사전 등록 5-3절(판정 화면)의 문구·키·저장 값이 실제 판정 화면 코드와 같은가.

판정 화면은 확정 커밋 시점으로 고정한다(docs/qa-preregistration.md 5-3절). 화면 코드만 바뀌거나 문서만 바뀌면
여기서 걸린다. 프론트 코드는 글자로만 읽는다(실행하지 않는다).
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "docs" / "qa-preregistration.md"
LOGIC = REPO / "frontend" / "src" / "components" / "blindAdjudicationLogic.ts"

EXPECTED = {
    "question_existing": "이 라벨은 수정이 필요한가?",
    "question_missing": "이 객체의 라벨이 누락됐는가?",
    "buttons": [("1", "오류 있음", "hit"), ("2", "오류 없음", "miss"), ("3", "판단 보류", "hold")],
}


def _section_5_3(text: str) -> str:
    start = text.index("### 5-3.")
    end = text.index("### 5-4.", start)
    return text[start:end]


def prereg_ui() -> dict:
    section = _section_5_3(PREREG.read_text(encoding="utf-8"))
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2:
            rows[cells[0]] = cells[1]
    q = lambda key: re.fullmatch(r'"([^"]+)"', rows[key]).group(1)
    buttons = re.findall(r"키 `(\d)` → \"([^\"]+)\" → `(\w+)`", rows["키·저장 값"])
    labels = re.findall(r'"([^"]+)"', rows["버튼 (두 화면 공통)"])
    return {"question_existing": q("기존 라벨 질문"), "question_missing": q("누락 후보 질문"),
            "buttons": buttons, "button_labels": labels}


def frontend_ui() -> dict:
    src = LOGIC.read_text(encoding="utf-8")
    const = lambda name: re.search(rf'export const {name} = "([^"]+)";', src).group(1)
    buttons = re.findall(r'\{\s*verdict:\s*"(\w+)",\s*label:\s*"([^"]+)",\s*key:\s*"(\d)"\s*\}', src)
    return {"question_existing": const("QUESTION_EXISTING"),
            "question_missing": const("QUESTION_MISSING"),
            "buttons": [(k, label, v) for v, label, k in buttons]}


def test_사전_등록_5_3절은_사용자가_정한_문구다():
    ui = prereg_ui()
    assert ui["question_existing"] == EXPECTED["question_existing"]
    assert ui["question_missing"] == EXPECTED["question_missing"]
    assert ui["buttons"] == EXPECTED["buttons"]
    assert ui["button_labels"] == [label for _, label, _ in EXPECTED["buttons"]]


@pytest.mark.skipif(not LOGIC.is_file(), reason="프론트 코드가 없는 환경")
def test_판정_화면_코드의_문구_키_저장_값이_사전_등록과_같다():
    pre, fe = prereg_ui(), frontend_ui()
    assert fe["question_existing"] == pre["question_existing"]
    assert fe["question_missing"] == pre["question_missing"]
    assert fe["buttons"] == pre["buttons"]
