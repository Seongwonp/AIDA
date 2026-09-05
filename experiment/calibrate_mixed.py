"""혼합 오류 조건으로 "2차 유형 신뢰도"를 잰다 (docs/21 F 재보정).

F에서 유형 신뢰도를 "대표 유형일 때 / 아닐 때"로 갈라 실측했는데, 보정에 쓴
26개 조건은 각각 오류 유형이 하나뿐이었다. 그래서 "아닐 때"의 값(예: 누락
4.3%)은 사실상 **"그 유형이 아예 없을 때"**의 값이고, 실제로 두 유형이 섞인
데이터셋에서 2차 유형이 얼마나 미더운지는 알 수 없었다.

여기서는 primary 30% + secondary 15%로 섞은 조건을 진단해, 대표 유형이 아닌
**secondary 유형 findings의 정밀도**를 잰다. 이 값이 4.3%보다 훨씬 높다면
현재 상수가 2차 오류를 과도하게 눌러 감추고 있다는 뜻이다.

학습은 하지 않는다 — 라벨 단위 진단은 clean 모델로 추론만 하므로
(diagnose_labels.run) 혼합 라벨만 있으면 된다.

사용법:
  python calibrate_mixed.py --limit 80
"""
import argparse
import json
from pathlib import Path

from PIL import Image

import config
from diagnose_labels import IMAGE_SUFFIXES, run
from label_diagnosis import iou, present_types, rescore, severity_for, summarize

MISSING_MATCH_IOU = 0.4


def _is_real_error(finding, entry: dict, images_dir: Path) -> bool:
    """이 finding이 실제로 주입된 오류 박스를 가리키는가."""
    if finding.suspicion == "missing":
        with Image.open(images_dir / finding.image) as img:
            img_w, img_h = img.width, img.height
        for cx, cy, w, h in entry["dropped"]:
            gt = ((cx - w / 2) * img_w, (cy - h / 2) * img_h,
                  (cx + w / 2) * img_w, (cy + h / 2) * img_h)
            if iou(finding.box, gt) >= MISSING_MATCH_IOU:
                return True
        return False

    if finding.label_index is None:
        return False
    if finding.label_index in entry["errored"]:
        return True
    # 중복 쌍은 원본을 지목해도 같은 자리를 보게 되므로 정답으로 인정한다
    # (evaluate_box_accuracy._errored_index_for와 같은 규칙)
    idx = finding.label_index + 1
    if idx in entry["errored"]:
        types = entry.get("errored_types", [])
        pos = entry["errored"].index(idx)
        return pos < len(types) and types[pos] == "duplicate"
    return False


def score_mixed(mixed: config.MixedCondition, limit: int | None) -> dict:
    root = config.MIXED_CONDITIONS_DIR / mixed.name
    images_dir, labels_dir = root / "images" / "train", root / "labels" / "train"
    findings, total_labels, _fit = run(images_dir, labels_dir, limit)
    record = json.loads((root / "injection_record.json").read_text(encoding="utf-8"))

    summary = summarize(findings, total_labels)
    dominant = summary["dominant_type"] if summary["systematic"] else None
    findings = rescore(findings, summary)

    # 유형별로 (정답 수, 전체 수)를 세되, 대표 유형인지에 따라 나눈다
    present = present_types(summary)
    per_type: dict[str, dict[str, list[int]]] = {}
    scored: list[dict] = []
    for f in findings:
        entry = record.get(Path(f.image).stem, {"errored": [], "dropped": []})
        correct = _is_real_error(f, entry, images_dir)
        bucket = per_type.setdefault(f.suspicion, {"dominant": [0, 0], "secondary": [0, 0]})
        key = "dominant" if f.suspicion == dominant else "secondary"
        bucket[key][1] += 1
        if correct:
            bucket[key][0] += 1
        # 두 규칙의 심각도를 나란히 계산해둔다 (A/B 비교용)
        scored.append({
            "correct": correct,
            "suspicion": f.suspicion,
            # confidence를 빼먹으면 제품이 실제로 쓰는 심각도가 아니라 옛 공식을
            # 비교하게 된다 — 실제로 한 번 그래서 값이 바이트 단위로 안 변했다.
            "severity_present": severity_for(
                f.suspicion, f.raw_signal, is_present=f.suspicion in present,
                confidence=f.confidence),
            "severity_dominant_only": severity_for(
                f.suspicion, f.raw_signal, is_present=f.suspicion == dominant,
                confidence=f.confidence),
        })

    return {
        "name": mixed.name,
        "primary_type": mixed.primary_type,
        "secondary_type": mixed.secondary_type,
        "predicted_dominant": dominant,
        # 진단이 primary를 대표 유형으로 제대로 골랐는가 — 이게 틀리면
        # 2차 유형 신뢰도 측정 자체가 의미를 잃는다
        "dominant_matches_primary": dominant == mixed.primary_type,
        "per_type": per_type,
        # 유형별 비율 — 2차 유형이 계통적 임계값(SYSTEMATIC_ERROR_RATIO)을
        # 넘는지가 "존재함/노이즈"를 가르는 실용적 기준이 될 수 있다
        "by_type": summary["by_type"],
        "scored": scored,
    }


def main():
    parser = argparse.ArgumentParser(description="혼합 조건 2차 유형 신뢰도 보정")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()

    rows = []
    for i, mixed in enumerate(config.MIXED_CONDITIONS, 1):
        print(f"[{i}/{len(config.MIXED_CONDITIONS)}] {mixed.name} ...", flush=True)
        rows.append(score_mixed(mixed, args.limit))

    print(f"\n{'조건':<24} {'primary':<14} {'예측 대표':<14} 일치")
    print("-" * 62)
    for r in rows:
        print(f"{r['name']:<24} {r['primary_type']:<14} "
              f"{str(r['predicted_dominant']):<14} {'O' if r['dominant_matches_primary'] else 'X'}")

    # 유형별 2차 신뢰도 집계 — 그 유형이 데이터셋에 존재하지만 대표는 아닐 때
    agg: dict[str, list[int]] = {}
    for r in rows:
        # secondary로 설계된 유형만 모은다 (primary는 대표라 이미 F에서 쟀다)
        sec = r["secondary_type"]
        bucket = r["per_type"].get(sec, {}).get("secondary")
        if not bucket:
            continue
        cur = agg.setdefault(sec, [0, 0])
        cur[0] += bucket[0]
        cur[1] += bucket[1]

    print(f"\n{'2차 유형':<16} {'정밀도':>10} {'건수':>8}   현재 상수(부재 시)")
    print("-" * 60)
    from label_diagnosis import TYPE_RELIABILITY_NOISE
    calibrated = {}
    for name, (tp, n) in sorted(agg.items(), key=lambda kv: -kv[1][1]):
        prec = tp / n if n else 0.0
        calibrated[name] = round(prec, 4)
        current = TYPE_RELIABILITY_NOISE.get(name, 0.5)
        print(f"{name:<16} {prec * 100:>9.1f}% {n:>8}   {current * 100:.1f}%")

    from label_diagnosis import SYSTEMATIC_ERROR_RATIO
    print(f"\n2차 유형이 계통적 임계값({SYSTEMATIC_ERROR_RATIO:.0%})을 넘는가")
    print("-" * 60)
    for r in rows:
        sec = r["secondary_type"]
        ratio = next((t["ratio"] for t in r["by_type"] if t["suspicion"] == sec), 0.0)
        mark = "O" if ratio >= SYSTEMATIC_ERROR_RATIO else "X"
        print(f"  {r['name']:<24} {sec:<14} {ratio * 100:>5.1f}%  {mark}")

    # A/B: 규칙 변경이 혼합 데이터셋의 재검수 목록 순서를 실제로 개선했는가.
    # 같은 findings를 두 규칙으로 각각 정렬해 상위권 정밀도를 비교한다 —
    # 판정(TP/FP)은 순서와 무관하므로 추론을 다시 돌릴 필요가 없다.
    print(f"\n혼합 조건 재검수 목록 상위권 정밀도 (1등만 승격 → 존재하면 승격)")
    print("-" * 60)
    for frac in (0.1, 0.25, 0.5, 1.0):
        olds, news = [], []
        for r in rows:
            scored = r["scored"]
            k = max(1, int(len(scored) * frac))
            old_sorted = sorted(scored, key=lambda x: -x["severity_dominant_only"])
            new_sorted = sorted(scored, key=lambda x: -x["severity_present"])
            olds.append(sum(x["correct"] for x in old_sorted[:k]) / k)
            news.append(sum(x["correct"] for x in new_sorted[:k]) / k)
        o = sum(olds) / len(olds)
        n = sum(news) / len(news)
        print(f"  상위 {int(frac * 100):>3}%: {o * 100:>5.1f}% → {n * 100:>5.1f}%  "
              f"({(n - o) * 100:+.1f}%p)")

    # 규칙 변경의 진짜 목적: 2차 오류가 재검수 목록에 실제로 **보이는가**.
    # 정밀도만 보면 놓치는 부분이다 — 1등 유형만 승격시키면 2차 오류는 진짜
    # 오류인데도 노이즈 신뢰도로 목록 바닥에 깔려, 상위권만 훑는 검수자에게는
    # 없는 것과 같아진다.
    print(f"\n2차 오류가 상위 100건 안에 몇 개나 들어오는가")
    print(f"{'조건':<24} {'2차유형':<14} {'1등만 승격':>10} {'존재하면 승격':>14}")
    print("-" * 66)
    tot_old = tot_new = 0
    for r in rows:
        sec, scored = r["secondary_type"], r["scored"]
        old_top = sorted(scored, key=lambda x: -x["severity_dominant_only"])[:100]
        new_top = sorted(scored, key=lambda x: -x["severity_present"])[:100]
        o = sum(1 for x in old_top if x["suspicion"] == sec and x["correct"])
        n = sum(1 for x in new_top if x["suspicion"] == sec and x["correct"])
        tot_old += o
        tot_new += n
        print(f"{r['name']:<24} {sec:<14} {o:>10} {n:>14}")
    print(f"{'합계':<24} {'':<14} {tot_old:>10} {tot_new:>14}")

    out = config.EXPERIMENT_ROOT / "mixed_calibration.json"
    out.write_text(json.dumps(
        {"secondary_reliability": calibrated,
         "conditions": [{k: v for k, v in r.items() if k != "scored"} for r in rows]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 → {out}")


if __name__ == "__main__":
    main()
