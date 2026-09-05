"""화면 라벨이 실험 코드의 판정 유형을 전부 덮는가.

실험(`experiment/label_diagnosis.py`)이 내는 판정 유형과 백엔드가 한글로
바꿔주는 표(`SUSPICION_LABELS`)는 **서로 다른 언어의 서로 다른 파일**에
있어서 조용히 어긋난다. 실제로 그랬다 — 다중 클래스를 넣으면서 새 유형
`class_mismatch`를 만들었는데 백엔드 표에 안 넣어서, 화면에 영어 타입명이
그대로 노출됐다.

이 프로젝트에서 반복해서 나온 사고 유형이라(하드코딩된 목록이 새 항목을
놓친다) 검사로 고정한다.

여기서는 `TYPE_RELIABILITY_PRESENT`을 유형의 정본으로 본다. 모든 판정 유형은
"그 유형이 있을 때의 신뢰도"를 가져야 하므로, 새 유형을 만들면 반드시 거기
들어간다.
"""
import re
import sys
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).resolve().parents[2] / "experiment"


def canonical_types() -> set[str]:
    """실험 코드가 내는 판정 유형. 무거운 의존성 없이 소스에서 읽는다.

    label_diagnosis를 import하면 ultralytics·torch까지 딸려와 백엔드
    테스트가 느려지고, 그 패키지가 없는 환경에서는 아예 못 돈다.
    """
    src = (EXPERIMENT / "label_diagnosis.py").read_text(encoding="utf-8")
    m = re.search(r"TYPE_RELIABILITY_PRESENT\s*=\s*\{(.*?)\n\}", src, re.S)
    assert m, "TYPE_RELIABILITY_PRESENT을 못 찾았다 — 이름이 바뀌었나?"
    return set(re.findall(r'"(\w+)"\s*:', m.group(1)))


def backend_labels() -> set[str]:
    from app.routers import upload
    return set(upload.SUSPICION_LABELS)


@pytest.mark.skipif(not (EXPERIMENT / "label_diagnosis.py").exists(),
                    reason="experiment/ 가 없는 환경")
def test_every_type_has_a_korean_label():
    """라벨이 빠지면 화면에 'class_mismatch' 같은 영어가 그대로 뜬다."""
    missing = canonical_types() - backend_labels()
    assert not missing, (
        f"한글 라벨이 없는 판정 유형: {sorted(missing)} — "
        f"backend/app/routers/upload.py의 SUSPICION_LABELS에 추가할 것")


@pytest.mark.skipif(not (EXPERIMENT / "label_diagnosis.py").exists(),
                    reason="experiment/ 가 없는 환경")
def test_no_label_for_a_type_that_no_longer_exists():
    """반대 방향. 없는 유형의 라벨이 남아 있으면 유형이 사라진 걸 못 알아챈다."""
    stale = backend_labels() - canonical_types()
    assert not stale, (
        f"실험 코드에 없는 유형의 라벨: {sorted(stale)} — "
        f"유형이 사라졌거나 이름이 바뀌었다")


def test_domain_robustness_table_uses_known_types():
    """도메인 강건성 표의 키도 같은 유형이어야 한다.

    이 표는 화면에서 "이 유형을 얼마나 믿을 수 있나"를 보여주는데, 키가
    어긋나면 그 유형만 조용히 표에서 빠진다.
    """
    from app.routers import upload
    unknown = set(upload.DOMAIN_ROBUSTNESS) - backend_labels()
    assert not unknown, f"라벨 표에 없는 유형: {sorted(unknown)}"


def test_cross_dataset_table_is_a_subset():
    """데이터셋 간 실측치(docs/21 AI)도 마찬가지."""
    from app.routers import upload
    unknown = set(upload.CROSS_DATASET_ROBUSTNESS) - backend_labels()
    assert not unknown, f"라벨 표에 없는 유형: {sorted(unknown)}"
