"""AG의 설명을 검증한다 — 잘 맞는 자는 예측이 결정 경계에서 먼가?

AG에서 자 4종의 안정성 순서(±2.20 / 2.59 / 3.27 / 5.45)가 정확도 순서와
거의 같은 걸 보고 이렇게 설명했다: **자가 데이터에 잘 맞으면 예측이 결정
경계에서 멀리 떨어져 있어, 학습 시드가 바뀌어도 판정이 잘 안 뒤집힌다.**

그건 관찰에서 나온 이야기이지 검증이 아니다. 여기서 직접 본다.

진단이 쓰는 문턱은 label_diagnosis.py에 있다:
  - MISSING_CONFIDENCE_THRESHOLD (0.70): 이 위여야 "라벨이 빠졌다"고 말한다
  - CLASS_MISMATCH_CONFIDENCE_THRESHOLD (0.60): 클래스 오기입 판정 문턱
  - 매칭 IoU (0.4)
문턱 근처에 예측이 몰려 있으면, 모델이 조금만 달라져도 그 예측들이 문턱을
넘나들며 판정이 뒤집힌다. 그래서 **문턱 근처 예측의 비율**이 불안정성의
직접적인 대리 지표다.

자마다 아는 클래스가 다르므로(먼 이동 자는 Car만) 두 가지로 잰다:
전체 예측, 그리고 Car 예측만. 뒤엣것이 자들을 같은 잣대로 놓는다.

사용법:
  AIDA_CLASSES=... AIDA_FRAME_SELECT=cyclist_rich python check_confidence_margin.py
"""
import json
import statistics
import sys
from pathlib import Path

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# AG에서 쓴 자 4종. 시드 42 하나로 본다 — 여기서 보려는 건 시드 사이의
# 차이가 아니라 "이 자의 예측이 문턱에서 얼마나 떨어져 있나"다.
RULERS = [
    ("자기 도메인", "runs_mc_cyclist_rich"),
    ("먼 이동(1C)", "runs"),
    ("약한 이동", "runs_mc"),
    ("넓은 자(800)", "runs_mc_broad_n800"),
]

# 판정을 가르는 문턱 근처 ±0.10 구간. 이 안의 예측은 모델이 조금만
# 달라져도 반대편으로 넘어간다.
THRESHOLDS = (0.60, 0.70)
BAND = 0.10


def margins(confidences: list[float]) -> dict:
    """문턱에서 얼마나 떨어져 있는가."""
    if not confidences:
        return {}
    near = sum(1 for c in confidences
               if any(abs(c - t) <= BAND for t in THRESHOLDS))
    # 가장 가까운 문턱까지의 거리. 클수록 판정이 안 뒤집힌다.
    dists = [min(abs(c - t) for t in THRESHOLDS) for c in confidences]
    return {
        "n": len(confidences),
        "mean_conf": statistics.mean(confidences),
        "near_ratio": near / len(confidences),
        "mean_margin": statistics.mean(dists),
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="예측이 판정 문턱에서 얼마나 먼가")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from ultralytics import YOLO

    images_dir = config.CONDITIONS_DIR / "clean" / "images" / "train"
    paths = sorted(p for p in images_dir.iterdir()
                   if p.suffix.lower() in {".png", ".jpg", ".jpeg"})[:args.limit]
    if not paths:
        raise SystemExit(f"{images_dir}에 이미지가 없다")
    print(f"이미지 {len(paths)}장 · 문턱 {THRESHOLDS} ±{BAND}\n")

    results = {}
    for label, base in RULERS:
        weights = config.EXPERIMENT_ROOT / base / "clean" / "weights" / "best.pt"
        if not weights.exists():
            print(f"  {label}: {weights} 없음 — 건너뜀")
            continue
        model = YOLO(str(weights))
        all_conf, car_conf = [], []
        for path in paths:
            r = model.predict(str(path), verbose=False)[0]
            for box in r.boxes:
                c = float(box.conf[0])
                all_conf.append(c)
                # 클래스 0은 어느 구성에서나 Car다(config.CLASS_NAMES 순서)
                if int(box.cls[0]) == 0:
                    car_conf.append(c)
        results[label] = {"all": margins(all_conf), "car": margins(car_conf)}
        a, c = results[label]["all"], results[label]["car"]
        print(f"■ {label}")
        print(f"    전체    예측 {a['n']:5d}개  평균신뢰도 {a['mean_conf']:.3f}  "
              f"문턱근처 {a['near_ratio']*100:5.1f}%  평균여유 {a['mean_margin']:.3f}")
        print(f"    Car만   예측 {c['n']:5d}개  평균신뢰도 {c['mean_conf']:.3f}  "
              f"문턱근처 {c['near_ratio']*100:5.1f}%  평균여유 {c['mean_margin']:.3f}")

    # AG가 예측한 순서: 자기 도메인 < 먼 이동 < 넓은 자 < 약한 이동
    # (안정적일수록 문턱 근처가 적어야 한다)
    print("\nAG의 안정성 순서와 대조 (Car 예측 기준)")
    print(f"  {'자':<14}{'AG 표준편차':>12}{'문턱근처':>10}{'평균여유':>10}")
    ag_sd = {"자기 도메인": 2.20, "먼 이동(1C)": 2.59, "넓은 자(800)": 3.27,
             "약한 이동": 5.45}
    rows = [(l, ag_sd[l], results[l]["car"]) for l, _ in RULERS if l in results]
    for label, sd, c in sorted(rows, key=lambda r: r[1]):
        print(f"  {label:<14}{sd:>11.2f}{c['near_ratio']*100:>9.1f}%{c['mean_margin']:>10.3f}")

    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"\n저장 → {args.out}")


if __name__ == "__main__":
    main()
