"""실행 기록용 환경 확인 — 자 가중치 SHA-256, cleanlab·ultralytics·torch 버전, 커밋.

사용법: python check_run_environment.py --ruler runs_nuimages/car_v1_e100/weights/best.pt --out env.json
가중치가 없으면 없다고 적는다(대체하지 않는다). 이 노트북에는 가중치가 없다 — 데스크탑에서 돌린다.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruler_check import sha256_of  # noqa: E402


def version_of(name: str) -> str | None:
    try:
        mod = __import__(name)
    except Exception:
        return None
    return getattr(mod, "__version__", "unknown")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruler", default="runs_nuimages/car_v1_e100/weights/best.pt")
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    weights = root / a.ruler
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=str(root), timeout=20).stdout.strip() or None
    except Exception:
        commit = None
    out = {
        "python": sys.version.split()[0], "platform": platform.platform(),
        "git_commit": commit,
        "ruler": {"path": a.ruler, "exists": weights.is_file(),
                  "sha256": sha256_of(weights) if weights.is_file() else None,
                  "size_bytes": weights.stat().st_size if weights.is_file() else None},
        "packages": {n: version_of(n) for n in ("cleanlab", "ultralytics", "torch", "numpy")},
        "note": "가중치가 없으면 sha256은 None이다. 다른 자로 대체하지 않는다.",
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
