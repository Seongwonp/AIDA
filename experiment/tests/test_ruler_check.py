"""외부 자 확인 — 없으면 멈추고, 해시가 다르면 멈추고, 기본 자로 되돌아가지 않는다."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ruler_check as R  # noqa: E402


def test_환경변수_자는_해시가_맞아야_열린다(tmp_path):
    w = tmp_path / "best.pt"; w.write_bytes(b"weights")
    path, rec = R.resolve_ruler({R.ENV_WEIGHTS: str(w), R.ENV_SHA256: R.sha256_of(w)}, tmp_path / "clean.pt")
    assert path == w and rec["source"] == R.ENV_WEIGHTS and rec["sha256_verified"] is True


def test_해시가_다르면_기본_자로_되돌아가지_않고_멈춘다(tmp_path):
    w = tmp_path / "best.pt"; w.write_bytes(b"weights")
    (tmp_path / "clean.pt").write_bytes(b"clean")
    with pytest.raises(R.RulerMismatch):
        R.resolve_ruler({R.ENV_WEIGHTS: str(w), R.ENV_SHA256: "0" * 64}, tmp_path / "clean.pt")


def test_자가_없으면_멈춘다(tmp_path):
    (tmp_path / "clean.pt").write_bytes(b"clean")
    with pytest.raises(R.RulerMismatch):
        R.resolve_ruler({R.ENV_WEIGHTS: str(tmp_path / "missing.pt")}, tmp_path / "clean.pt")


def test_환경변수가_없으면_기본_자와_그_해시다(tmp_path):
    c = tmp_path / "clean.pt"; c.write_bytes(b"clean")
    path, rec = R.resolve_ruler({}, c)
    assert path == c and rec["source"] == "default_clean" and rec["sha256"] == R.sha256_of(c)


def test_진단_실행기는_ruler_check를_거쳐_결과에_자를_적는다():
    src = (Path(__file__).resolve().parent.parent / "diagnose_labels.py").read_text(encoding="utf-8")
    assert "ruler_check.from_environ(CLEAN_WEIGHTS)" in src
    assert '"ruler": (fit or {}).get("ruler")' in src
