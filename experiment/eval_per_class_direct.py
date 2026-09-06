"""이름을 직접 받아 클래스별 mAP를 낸다.

evaluate_per_class.py는 config에 등록된 조건만 본다. AK의 정제 조건
(clean_subN, scale_m30_refined50)은 규모 실험 스크립트가 그때만 등록하는
것이라, 지금 환경에서는 가중치와 yaml이 있는데도 목록에 안 뜬다.

학습하지 않는다. 저장된 best.pt로 검증셋만 다시 돈다.
"""
import argparse, csv, sys
from pathlib import Path
import config
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from ultralytics import YOLO
    rows = []
    for i, name in enumerate(a.conditions, 1):
        w = config.RUNS_DIR / name / "weights" / "best.pt"
        y = config.DATA_YAML_DIR / f"{name}.yaml"
        if not w.exists() or not y.exists():
            print(f"[{i}/{len(a.conditions)}] {name} — 가중치/yaml 없음, 건너뜀")
            continue
        print(f"[{i}/{len(a.conditions)}] {name} ...", flush=True)
        m = YOLO(str(w)).val(data=str(y), imgsz=config.IMG_SIZE,
                             device=config.resolve_device(), verbose=False, plots=False)
        row = {"condition": name, "map50": round(float(m.box.map50), 4)}
        for idx, cid in enumerate(m.box.ap_class_index):
            row[f"map50_{config.CLASS_NAMES[int(cid)]}"] = round(float(m.box.ap50[idx]), 4)
        rows.append(row)

    fields = ["condition", "map50"] + [f"map50_{n}" for n in config.CLASS_NAMES]
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=fields); wr.writeheader()
        for r in rows: wr.writerow({k: r.get(k, "") for k in fields})
    print(f"저장 → {out}")


if __name__ == "__main__":
    main()
