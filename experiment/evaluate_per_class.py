"""조건별 클래스별 mAP — 저하가 어느 클래스에서 오는지 본다.

전체 mAP만 보면 교란이 하나 남는다. 다중 클래스 clean 모델은 mAP50 0.599로
Car 단일(0.876)보다 훨씬 약한데, 같은 라벨 오류에서 저하율이 더 크게 나온다.
이게 **클래스가 많아서**인지 **약한 모델이라 흔들릴 여지가 커서**인지 전체
숫자로는 못 가른다.

클래스별로 보면 갈린다:
- 오류를 주입한 클래스만 떨어지면 → 라벨 오류의 직접 효과
- 안 건드린 클래스까지 같이 떨어지면 → 학습이 통째로 불안정해진 것

학습을 다시 하지 않는다. 이미 저장된 best.pt로 검증셋만 다시 돌리므로
조건당 몇 초면 끝난다.

사용법:
  python evaluate_per_class.py                 # 학습 끝난 조건 전부
  python evaluate_per_class.py --conditions clean width_m30
"""
import argparse
import csv
import sys

import config

# Windows 콘솔(cp949)이 일부 문자를 못 찍어서 죽는 걸 막는다
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_CSV = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / \
    f"metrics_per_class{config._csuffix}.csv"


def trained_conditions() -> list:
    """가중치가 있는 조건만. 학습이 진행 중이어도 끝난 것까지는 잴 수 있다."""
    all_conditions = list(config.conditions_in_run_order())
    return [c for c in all_conditions
            if (config.RUNS_DIR / c.name / "weights" / "best.pt").exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description="조건별 클래스별 mAP")
    parser.add_argument("--conditions", nargs="+")
    args = parser.parse_args()

    from ultralytics import YOLO

    conditions = trained_conditions()
    if args.conditions:
        wanted = set(args.conditions)
        conditions = [c for c in conditions if c.name in wanted]
    if not conditions:
        raise SystemExit("가중치가 있는 조건이 없습니다 — 학습을 먼저 하세요")

    rows = []
    for i, c in enumerate(conditions, 1):
        weights = config.RUNS_DIR / c.name / "weights" / "best.pt"
        yaml_path = config.DATA_YAML_DIR / f"{c.name}.yaml"
        print(f"[{i}/{len(conditions)}] {c.name} ...", flush=True)
        metrics = YOLO(str(weights)).val(
            data=str(yaml_path), imgsz=config.IMG_SIZE,
            device=config.resolve_device(), verbose=False, plots=False,
        )
        row = {"condition": c.name, "type": c.type, "magnitude": c.magnitude,
               "map50": round(float(metrics.box.map50), 4)}
        # ap50는 "검증셋에 등장한 클래스" 순서다. 클래스 인덱스로 되짚지 않으면
        # 한 클래스라도 검증셋에서 빠졌을 때 이름이 통째로 밀린다.
        present = list(metrics.box.ap_class_index)
        for idx, cls_id in enumerate(present):
            name = config.CLASS_NAMES[int(cls_id)]
            row[f"map50_{name}"] = round(float(metrics.box.ap50[idx]), 4)
        rows.append(row)

    fields = ["condition", "type", "magnitude", "map50"] + \
        [f"map50_{n}" for n in config.CLASS_NAMES]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)}개 조건 → {OUT_CSV}")
    report(rows)


def report(rows: list[dict]) -> None:
    """clean 대비 클래스별 저하율 — 저하가 어느 클래스에서 오는지 바로 보이게.

    오류는 클래스를 가리지 않고 주입하므로, 특정 클래스만 크게 떨어진다면
    그건 주입량이 아니라 그 클래스가 라벨 노이즈에 약하다는 뜻이다.
    """
    clean = next((r for r in rows if r["condition"] == "clean"), None)
    if clean is None:
        print("clean 조건이 없어 저하율은 못 냅니다 (절대값은 CSV 참고)")
        return

    cols = [f"map50_{n}" for n in config.CLASS_NAMES]
    header = f"{'조건':<16}{'전체':>8}" + "".join(f"{n:>13}" for n in config.CLASS_NAMES)
    print("\nclean 대비 저하율 (%) — 오류는 클래스 구분 없이 주입했다")
    print(f"{'clean 절대값':<16}{clean['map50']:>8.3f}"
          + "".join(f"{clean.get(c, 0):>13.3f}" for c in cols))
    print(header)
    print("-" * len(header))
    for r in rows:
        if r["condition"] == "clean":
            continue
        cells = []
        for c in cols:
            base, cur = clean.get(c), r.get(c)
            cells.append(f"{(base - cur) / base * 100:>12.1f}%"
                         if base and cur is not None else f"{'-':>13}")
        overall = (clean["map50"] - r["map50"]) / clean["map50"] * 100
        print(f"{r['condition']:<16}{overall:>7.1f}%" + "".join(cells))


if __name__ == "__main__":
    main()
