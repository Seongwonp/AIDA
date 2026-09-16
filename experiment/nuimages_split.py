"""nuImages **train**을 자 학습용과 적합도 확인용으로 나눈다 (docs/nuimages-data-plan.md).

- **val·test는 읽지 않는다.** 평가용 부분은 사전 등록 전까지 열지 않는다 — 이 스크립트는 train이
  아닌 분할 이름을 거부한다.
- **주행 기록(log) 단위로 나눈다.** 같은 기록의 이웃 프레임이 학습과 확인에 갈라 들어가면 확인
  수치가 부풀려진다.
- **씨앗으로 다시 만들 수 있다.** 기록·토큰을 정렬한 뒤 섞는다.

    ./venv/Scripts/python.exe nuimages_split.py --src D:/AIDA-eval/nuimages/all \\
        --version v1.0-train --out D:/AIDA-eval/nuimages/splits/dev_v1 \\
        --fit-check-images 500 --ruler-train-images 3200 --seed 20260916

출력: `fit_check_tokens.txt`, `ruler_train_tokens.txt`(sample_data 토큰 한 줄에 하나),
`split_summary.json`. 토큰 목록은 `nuimages_to_yolo.py --tokens-file`로 넘긴다.
"""
import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

TABLES = ("log", "sensor", "calibrated_sensor", "sample", "sample_data")


def check_version(version: str) -> None:
    if not version.startswith("v1.0-train"):
        raise ValueError(f"train 분할만 읽는다 — 평가용 부분을 열지 않는다: {version}")


def load_tables(src_root: Path, version: str) -> dict[str, list[dict]]:
    check_version(version)
    root = Path(src_root) / version
    return {name: json.loads((root / f"{name}.json").read_text(encoding="utf-8")) for name in TABLES}


def _keyframes(tables: dict, cameras: set[str] | None) -> list[dict]:
    samples = {s["token"]: s for s in tables["sample"]}
    logs = {log["token"]: log for log in tables["log"]}
    sensors = {s["token"]: s["channel"] for s in tables["sensor"]}
    calibrated = {c["token"]: c["sensor_token"] for c in tables["calibrated_sensor"]}
    rows = []
    for d in tables["sample_data"]:
        if not d["is_key_frame"]:
            continue
        camera = sensors[calibrated[d["calibrated_sensor_token"]]]
        if cameras is not None and camera not in cameras:
            continue
        log_token = samples[d["sample_token"]]["log_token"]
        rows.append({"sample_data_token": d["token"], "log_token": log_token,
                     "location": logs[log_token].get("location"), "camera": camera,
                     "filename": d["filename"]})
    return rows


def _take_logs(logs: list[str], by_log: dict, target: int, taken: set[str]) -> list[str]:
    """아직 안 쓴 기록을 순서대로 통째로 모은다 — 키프레임 수가 목표에 닿을 때까지."""
    chosen, count = [], 0
    for log in logs:
        if count >= target:
            break
        if log in taken:
            continue
        chosen.append(log)
        count += len(by_log[log])
    return chosen


def split_by_log(tables: dict, fit_check_images: int, ruler_train_images: int, seed: int,
                 cameras: set[str] | None = None, ruler_val_images: int = 0) -> dict:
    """확인용과 학습 검증용은 **기록을 통째로** 목표 수에 닿을 때까지 모으고, 나머지 기록에서
    학습용을 뽑는다. 세 묶음은 기록이 서로 겹치지 않는다.

    학습 검증용(`ruler_val`)은 학습 중 best.pt를 고르는 데만 쓴다 — 확인용으로 고르면 확인 수치가
    부풀려진다.
    """
    rows = _keyframes(tables, cameras)
    by_log: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["sample_data_token"]):
        by_log[r["log_token"]].append(r)

    rng = random.Random(seed)
    logs = sorted(by_log)
    rng.shuffle(logs)

    fit_logs = _take_logs(logs, by_log, fit_check_images, set())
    val_logs = _take_logs(logs, by_log, ruler_val_images, set(fit_logs)) if ruler_val_images else []
    used = set(fit_logs) | set(val_logs)
    fit_check = [r for log in sorted(fit_logs) for r in by_log[log]]
    ruler_val = [r for log in sorted(val_logs) for r in by_log[log]]

    pool = sorted((r for log in logs if log not in used for r in by_log[log]),
                  key=lambda r: r["sample_data_token"])
    ruler_train = sorted(rng.sample(pool, min(ruler_train_images, len(pool))),
                         key=lambda r: r["sample_data_token"])

    summary = {
        "seed": seed,
        "cameras": sorted(cameras) if cameras else None,
        "keyframes_considered": len(rows),
        "logs_available": len(logs),
        "fit_check_images": len(fit_check),
        "fit_check_logs": len(fit_logs),
        "ruler_val_images": len(ruler_val),
        "ruler_val_logs": len(val_logs),
        "fit_check_by_location": dict(Counter(r["location"] for r in fit_check)),
        "ruler_train_images": len(ruler_train),
        "ruler_train_logs": len({r["log_token"] for r in ruler_train}),
        "ruler_train_by_location": dict(Counter(r["location"] for r in ruler_train)),
        "ruler_train_shortfall": max(0, ruler_train_images - len(ruler_train)),
        "ruler_train_by_camera": dict(Counter(r["camera"] for r in ruler_train)),
    }
    return {"fit_check": fit_check, "ruler_val": ruler_val, "ruler_train": ruler_train,
            "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description="nuImages train → 자 학습용 / 적합도 확인용 (기록 단위)")
    parser.add_argument("--src", required=True)
    parser.add_argument("--version", default="v1.0-train")
    parser.add_argument("--out", required=True)
    parser.add_argument("--fit-check-images", type=int, required=True)
    parser.add_argument("--ruler-train-images", type=int, required=True)
    parser.add_argument("--ruler-val-images", type=int, default=0,
                        help="학습 중 best.pt를 고르는 검증용 (확인용과 다른 기록)")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cameras", nargs="*")
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"이미 분할 결과가 있다 — 덮어쓰지 않는다: {out}")
    split = split_by_log(load_tables(Path(args.src), args.version), args.fit_check_images,
                         args.ruler_train_images, args.seed,
                         set(args.cameras) if args.cameras else None, args.ruler_val_images)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("fit_check", "ruler_val", "ruler_train"):
        (out / f"{name}_tokens.txt").write_text(
            "".join(r["sample_data_token"] + "\n" for r in split[name]), encoding="utf-8")
    summary = {**split["summary"], "version": args.version}
    (out / "split_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
