"""nuImages **val**에서 평가 표본을 주행 기록(log) 단위로 뽑는다 (docs/nuimages-data-plan.md).

**사전 등록 커밋이 있어야만 돈다.** 사전 등록 파일이 git에 커밋되어 있고 작업 폴더에서 바뀌지 않았는지
확인한 뒤에야 val 표를 연다. 표본 요약에 그 커밋을 적는다.

뽑는 규칙 — 기록을 씨앗으로 섞고, 기록마다 키프레임을 **최대 `per_log`장** 씨앗으로 뽑아 목표 수에
닿을 때까지 모은다. 기록 하나가 표본을 채우지 않게 하고, 집계는 기록을 묶음(`group_id`)으로
재표집한다. 목표 수·`per_log`·씨앗은 사전 등록(D3)에서 정한다.

    ./venv/Scripts/python.exe nuimages_eval_sample.py --src D:/AIDA-eval/nuimages/all \\
        --version v1.0-val --preregistration docs/qa-preregistration.md \\
        --images 300 --per-log 10 --seed <사전 등록 값> --out D:/AIDA-eval/nuimages/splits/eval_v1

출력: `eval_tokens.txt`(`nuimages_to_yolo.py --tokens-file`로 넘긴다), `sample_summary.json`.
"""
import argparse
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from nuimages_split import TABLES, _keyframes

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_VERSION = "v1.0-val"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


# 사전 등록에 남은 빈칸 표시. 하나라도 있으면 **커밋되어 있어도** 사전 등록이 아니다
# (docs/qa-preregistration.md 11절 "하나라도 비어 있으면 이 문서는 사전 등록이 아니다").
# 이 표시들을 사전 등록 본문의 설명 문장에 그대로 쓰지 않는다 — 쓰면 완성본도 거부된다.
UNFILLED_MARKERS = ("[미기입", "[실행 전 기입]", "【")


def unfilled_markers(text: str) -> list[dict]:
    """빈칸 표시가 남은 줄. 줄 번호(1부터)·표시·줄 앞부분."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for marker in UNFILLED_MARKERS:
            if marker in line:
                found.append({"line": number, "marker": marker, "text": line.strip()[:80]})
    return found


def check_preregistration(repo: Path, path: str) -> str:
    """사전 등록 파일이 커밋되어 있고, 바뀌지 않았고, **빈칸 표시가 없으면** 그 파일의 마지막 커밋을 돌려준다."""
    if _git(repo, "ls-files", "--error-unmatch", path).returncode != 0:
        raise ValueError(f"사전 등록 파일이 git에 커밋되어 있지 않다 — val을 열지 않는다: {path}")
    if _git(repo, "diff", "--quiet", "HEAD", "--", path).returncode != 0:
        raise ValueError(f"사전 등록 파일에 커밋하지 않은 변경이 있다 — val을 열지 않는다: {path}")
    # 바이트로 받아 UTF-8로 읽는다 — Windows 기본 인코딩(cp949)으로 읽으면 표시를 놓칠 수 있다.
    shown = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{Path(path).as_posix()}"],
                           capture_output=True)
    if shown.returncode != 0:
        raise ValueError(f"커밋된 사전 등록을 읽지 못했다 — val을 열지 않는다: {path}")
    try:
        committed = shown.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"사전 등록이 UTF-8이 아니다 — val을 열지 않는다: {path}") from exc
    left = unfilled_markers(committed)
    if left:
        where = ", ".join(f"{m['line']}행 {m['marker']}" for m in left[:10])
        raise ValueError(f"사전 등록에 채우지 않은 칸이 {len(left)}곳 남았다 — val을 열지 않는다: {where}")
    commit = _git(repo, "log", "-1", "--format=%H", "--", path).stdout.strip()
    if not commit:
        raise ValueError(f"사전 등록 파일의 커밋을 찾지 못했다: {path}")
    return commit


def sample_by_log(tables: dict, images: int, per_log: int, seed: int,
                  cameras: set[str] | None = None) -> dict:
    if images < 1 or per_log < 1:
        raise ValueError(f"목표 수와 기록당 최대 수는 1 이상이다: {images}, {per_log}")
    rows = _keyframes(tables, cameras)
    by_log: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["sample_data_token"]):
        by_log[r["log_token"]].append(r)

    rng = random.Random(seed)
    logs = sorted(by_log)
    rng.shuffle(logs)
    picked: list[dict] = []
    for log in logs:
        need = images - len(picked)
        if need <= 0:
            break
        take = min(per_log, need, len(by_log[log]))
        picked.extend(rng.sample(by_log[log], take))
    picked.sort(key=lambda r: r["sample_data_token"])

    per_log_counts = Counter(r["log_token"] for r in picked)
    return {"rows": picked, "summary": {
        "seed": seed, "per_log": per_log, "cameras": sorted(cameras) if cameras else None,
        "images_target": images, "images": len(picked), "shortfall": max(0, images - len(picked)),
        "logs": len(per_log_counts), "max_per_log": max(per_log_counts.values(), default=0),
        "by_location": dict(Counter(r["location"] for r in picked)),
        "by_camera": dict(Counter(r["camera"] for r in picked)),
        # 개발/최종 경계 (사전 등록 D1). 이번 표본이 **소비한** val 기록과, 아직 열지 않은
        # 기록 수. 다음 평가는 소비한 기록을 다시 쓰지 않는다.
        "consumed_log_tokens": sorted(per_log_counts),
        "unconsumed_logs": len(logs) - len(per_log_counts),
    }}


def main() -> int:
    parser = argparse.ArgumentParser(description="nuImages val 평가 표본 (기록 단위, 사전 등록 뒤)")
    parser.add_argument("--src", required=True)
    parser.add_argument("--version", default=EVAL_VERSION)
    parser.add_argument("--preregistration", required=True, help="저장소 기준 경로 — 커밋되어 있어야 한다")
    parser.add_argument("--images", type=int, required=True)
    parser.add_argument("--per-log", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cameras", nargs="*")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.version != EVAL_VERSION:
        raise SystemExit(f"평가 표본은 {EVAL_VERSION}에서만 뽑는다: {args.version}")
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"이미 표본이 있다 — 덮어쓰지 않는다: {out}")
    commit = check_preregistration(REPO_ROOT, args.preregistration)   # val을 열기 전에

    root = Path(args.src) / args.version
    tables = {name: json.loads((root / f"{name}.json").read_text(encoding="utf-8")) for name in TABLES}
    result = sample_by_log(tables, args.images, args.per_log, args.seed,
                           set(args.cameras) if args.cameras else None)
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval_tokens.txt").write_text(
        "".join(r["sample_data_token"] + "\n" for r in result["rows"]), encoding="utf-8")
    summary = {**result["summary"], "version": args.version,
               "preregistration": args.preregistration, "preregistration_commit": commit}
    (out / "sample_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
