"""외부 자(가중치)의 확인 — 경로·SHA-256 (사전 등록 D1, nuImages 자 선택).

**잘못된 자로 조용히 대체되지 않게 한다.** 백엔드가 고른 자의 경로와 SHA-256을 환경변수로
넘기고, 진단은 그 파일을 열기 전에 해시를 다시 재서 다르면 멈춘다. 결과 JSON에는 실제로
연 파일과 해시를 적는다.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

ENV_WEIGHTS = "AIDA_RULER_WEIGHTS"
ENV_SHA256 = "AIDA_RULER_SHA256"


class RulerMismatch(RuntimeError):
    """넘겨받은 자가 없거나 해시가 다르다."""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_ruler(env: dict[str, str], default: Path) -> tuple[Path, dict]:
    """(열 가중치, 기록). 환경변수에 자가 있으면 그것, 없으면 `default`.

    환경변수의 자는 **반드시 있어야 하고**, SHA-256이 주어졌으면 같아야 한다. 없거나 다르면
    기본 자로 되돌아가지 않고 `RulerMismatch`다.
    """
    given = env.get(ENV_WEIGHTS)
    if given:
        path = Path(given)
        if not path.is_file():
            raise RulerMismatch(f"{ENV_WEIGHTS}가 가리키는 자가 없습니다: {path}")
        actual = sha256_of(path)
        expected = env.get(ENV_SHA256)
        if expected and expected.lower() != actual:
            raise RulerMismatch(
                f"자의 SHA-256이 다릅니다: 기대 {expected[:12]}…, 실제 {actual[:12]}… ({path})")
        return path, {"weights": str(path), "sha256": actual, "source": ENV_WEIGHTS,
                      "sha256_verified": bool(expected)}
    if not default.is_file():
        raise RulerMismatch(f"{default} 없음 — 해당 조건을 먼저 학습하세요")
    return default, {"weights": str(default), "sha256": sha256_of(default),
                     "source": "default_clean", "sha256_verified": False}


def from_environ(default: Path) -> tuple[Path, dict]:
    return resolve_ruler(dict(os.environ), default)
