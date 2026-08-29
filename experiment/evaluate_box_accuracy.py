"""박스 단위 진단 정확도 — "실제로 오류가 주입된 그 박스를 짚었는가".

evaluate_label_diagnosis.py가 재는 92.6%는 "데이터셋의 대표 오류 유형을
맞혔는가"다. 그건 고객에게 "당신 데이터셋엔 누락 라벨이 많습니다"라고 말할
근거는 되지만, "이 박스를 다시 보세요"라는 재검수 목록 자체가 맞는지는
말해주지 않는다. ROI 주장("의심 상위 30%만 재검수하면 된다")이 성립하려면
그 목록의 정밀도가 실제로 높아야 하므로, 여기서 그걸 잰다.

정답지는 error_injector.py가 라벨을 만들 때 남긴
`conditions/<name>/injection_record.json`이다:
  errored: 오류를 넣은 출력 라벨 인덱스 (크기/이동/중복)
  dropped: 누락시킨 박스의 정규화 좌표 (누락은 가리킬 인덱스가 없으므로)

채점:
  TP  진단이 지목한 박스가 실제로 오류 박스
  FP  멀쩡한 박스를 지목
  FN  오류 박스인데 못 잡음
  precision = TP/(TP+FP)  — 재검수 목록이 얼마나 알짜인가 (ROI의 근거)
  recall    = TP/(TP+FN)  — 실제 오류를 얼마나 놓치지 않는가

사용법:
  python evaluate_box_accuracy.py --limit 80
"""
import argparse
import csv
import json
from pathlib import Path

from PIL import Image

import config
from diagnose_labels import IMAGE_SUFFIXES, load_yolo_labels
from label_diagnosis import iou

# 누락 의심 예측 박스가 "지워진 그 박스"를 가리키는 것으로 인정할 최소 IoU.
# 위치가 이 정도로 겹치면 같은 객체를 지목했다고 본다.
MISSING_MATCH_IOU = 0.4


def load_injection_record(condition_name: str) -> dict:
    path = config.CONDITIONS_DIR / condition_name / "injection_record.json"
    if not path.exists():
        raise RuntimeError(
            f"{path} 없음 — error_injector.py를 다시 실행해 정답지를 생성하세요"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def score_condition(condition: config.Condition, limit: int | None) -> dict:
    """조건 하나에 대해 박스 단위 TP/FP/FN을 센다."""
    from diagnose_labels import run  # 지연 import — GPU 없는 환경에서도 모듈 로드는 되게

    root = config.CONDITIONS_DIR / condition.name
    images_dir, labels_dir = root / "images" / "train", root / "labels" / "train"
    findings, _ = run(images_dir, labels_dir, limit)
    record = load_injection_record(condition.name)

    # 평가 대상 이미지만 정답지에서 추린다 (limit을 걸면 일부만 돌기 때문)
    scanned = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if limit:
        scanned = scanned[:limit]
    scanned_stems = {p.stem for p in scanned}

    tp = fp = 0
    type_correct = 0  # TP 중 오류 "유형"까지 맞힌 건수
    matched_dropped: set[tuple[str, int]] = set()
    matched_errored: set[tuple[str, int]] = set()
    # 심각도 순위대로 (정답여부, 의심유형, 심각도)를 기록해둔다 — 우선순위가
    # 실제로 작동하는지(위에서부터 보면 알짜가 더 많은지) 재고, 유형별로
    # 신뢰도가 얼마나 다른지 분석하는 데 쓴다.
    verdicts_by_rank: list[tuple[bool, str, float]] = []

    findings = sorted(findings, key=lambda f: -f.severity)
    for f in findings:
        stem = Path(f.image).stem
        entry = record.get(stem, {"errored": [], "dropped": []})

        if f.suspicion == "missing":
            # 지워진 박스 좌표와 겹치는지로 판정
            img_path = images_dir / f.image
            with Image.open(img_path) as img:
                img_w, img_h = img.width, img.height
            hit_index = None
            best = MISSING_MATCH_IOU
            for i, (cx, cy, w, h) in enumerate(entry["dropped"]):
                gt = (
                    (cx - w / 2) * img_w, (cy - h / 2) * img_h,
                    (cx + w / 2) * img_w, (cy + h / 2) * img_h,
                )
                v = iou(f.box, gt)
                if v >= best:
                    best, hit_index = v, i
            if hit_index is not None:
                tp += 1
                type_correct += 1  # 누락을 누락이라 불렀으므로 유형도 맞음
                matched_dropped.add((stem, hit_index))
                verdicts_by_rank.append((True, f.suspicion, f.severity))
            else:
                fp += 1
                verdicts_by_rank.append((False, f.suspicion, f.severity))
        else:
            hit = _errored_index_for(condition.type, f.label_index, entry["errored"])
            if hit is not None:
                tp += 1
                matched_errored.add((stem, hit))
                if _type_matches(condition.type, f.suspicion):
                    type_correct += 1
                verdicts_by_rank.append((True, f.suspicion, f.severity))
            else:
                fp += 1
                verdicts_by_rank.append((False, f.suspicion, f.severity))

    total_injected = 0
    for stem in scanned_stems:
        entry = record.get(stem)
        if not entry:
            continue
        total_injected += len(entry["errored"]) + len(entry["dropped"])

    # 정밀도와 재현율의 분모가 다르다는 점이 중요하다.
    # - 정밀도: "우리가 보라고 한 박스 중 볼 가치가 있던 비율" → 진단 건수 기준.
    #   중복 쌍처럼 한 오류에 두 박스가 걸리면 둘 다 볼 가치가 있으므로 둘 다 센다.
    # - 재현율: "주입한 오류 중 몇 개를 찾아냈나" → 주입 건수 기준. 여기서 같은
    #   오류를 두 번 지목한 걸 2건으로 세면 재현율이 부풀려지므로, 중복 제거된
    #   matched_* 집합의 크기를 쓴다.
    caught = len(matched_errored) + len(matched_dropped)
    fn = max(total_injected - caught, 0)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = caught / total_injected if total_injected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "condition": condition.name,
        "type": condition.type,
        "magnitude": condition.magnitude,
        "injected": total_injected,
        "flagged": tp + fp,
        "tp": tp,
        "fp": fp,
        "caught": caught,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        # TP 중에서 유형까지 맞힌 비율 — 박스는 맞게 짚었는데 이유를 틀렸는지 본다
        "type_accuracy": round(type_correct / tp, 4) if tp else 0.0,
        "verdicts_by_rank": verdicts_by_rank,
    }


def precision_at_k(verdicts: list[tuple[bool, str, float]], k: int) -> float:
    """상위 k건만 봤을 때의 정밀도.

    제품의 핵심 주장이 "우선순위"이므로, 목록 전체의 정밀도보다 위에서부터
    k건을 봤을 때 알짜 비율이 더 중요하다 — 검수자는 위에서부터 일하다가
    예산이 떨어지면 멈추기 때문이다. 이 값이 전체 정밀도보다 높아야 심각도
    정렬이 실제로 작동한다고 말할 수 있다.
    """
    if not verdicts or k <= 0:
        return 0.0
    top = verdicts[:k]
    return sum(v[0] for v in top) / len(top)


def _errored_index_for(condition_type: str, label_index: int | None,
                        errored: list[int]) -> int | None:
    """지목한 라벨 인덱스가 실제 오류 박스면 그 정답 인덱스를 돌려준다.

    중복 조건은 예외를 둔다. error_injector가 원본 바로 뒤에 복제본을 끼워
    넣으므로 정답지에는 복제본 인덱스 j만 적히지만, 실제로는 j-1(원본)과
    j(복제본)가 한 쌍이고 **둘 중 무엇을 지목하든 검수자는 같은 자리를 보고
    하나를 지우게 된다.** 어느 쪽이 매칭될지는 예측 박스와의 IoU가 가르는
    우연이므로, 원본을 지목한 것을 오답으로 세면 정밀도가 실제보다 낮게
    나온다. 따라서 쌍 중 하나를 지목하면 정답으로 인정한다.
    """
    if label_index is None:
        return None
    if label_index in errored:
        return label_index
    if condition_type == "duplicate" and (label_index + 1) in errored:
        return label_index + 1
    return None


def _type_matches(condition_type: str, suspicion: str) -> bool:
    """진단이 부른 유형이 주입한 유형과 맞는지.

    회전은 AABB 외접 근사 때문에 크기 계열과 원리적으로 구분되지 않는다
    (evaluate_label_diagnosis.py 상단 주석의 기하 유도 참고).
    """
    if condition_type == "rotation":
        return suspicion in {"width", "height", "scale"}
    return condition_type == suspicion


def main():
    parser = argparse.ArgumentParser(description="박스 단위 진단 정확도 평가")
    parser.add_argument("--limit", type=int, default=80, help="조건당 이미지 수")
    parser.add_argument("--conditions", nargs="+", help="특정 조건만")
    args = parser.parse_args()

    conditions = [c for c in config.conditions_in_run_order() if c.type != "none"]
    if args.conditions:
        by_name = {c.name: c for c in config.CONDITIONS}
        conditions = [by_name[n] for n in args.conditions]

    rows = []
    for i, condition in enumerate(conditions, 1):
        print(f"[{i}/{len(conditions)}] {condition.name} ...", flush=True)
        rows.append(score_condition(condition, args.limit))

    print(f"\n{'조건':<14} {'주입':>5} {'지목':>5} {'TP':>5} {'FP':>5} {'놓침':>5} "
          f"{'정밀도':>7} {'재현율':>7} {'F1':>6} {'유형정확':>8}")
    print("-" * 88)
    for r in rows:
        print(f"{r['condition']:<14} {r['injected']:>5} {r['flagged']:>5} {r['tp']:>5} "
              f"{r['fp']:>5} {r['fn']:>5} "
              f"{r['precision']:>7.3f} {r['recall']:>7.3f} {r['f1']:>6.3f} {r['type_accuracy']:>8.3f}")

    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    injected = sum(r["injected"] for r in rows)
    caught = sum(r["caught"] for r in rows)
    micro_p = tp / (tp + fp) if (tp + fp) else 0.0
    micro_r = caught / injected if injected else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) else 0.0

    print(f"\n전체(micro): 지목 {tp + fp}건 중 TP {tp} / FP {fp}, "
          f"주입 {injected}건 중 {caught}건 검출")
    print(f"  정밀도 {micro_p * 100:.1f}%  재현율 {micro_r * 100:.1f}%  F1 {micro_f1 * 100:.1f}%")

    # 우선순위가 작동하는지: 조건별로 상위 k%만 봤을 때의 정밀도를 평균낸다.
    # 조건마다 지목 건수가 달라 절대 개수 대신 비율로 자른다.
    print("\n재검수 목록 상위권 정밀도 (심각도 순 정렬이 실제로 작동하는가)")
    pak: dict[str, float] = {}
    for frac in (0.1, 0.25, 0.5, 1.0):
        vals = []
        for r in rows:
            verdicts = r["verdicts_by_rank"]
            k = max(1, int(len(verdicts) * frac))
            vals.append(precision_at_k(verdicts, k))
        avg = sum(vals) / len(vals) if vals else 0.0
        pak[f"top_{int(frac * 100)}pct"] = round(avg, 4)
        print(f"  상위 {int(frac * 100):>3}%: {avg * 100:.1f}%")

    # 유형별 신뢰도 — 상위권 정밀도가 낮다면 "심각도 높은 유형이 실은 덜
    # 미덥다"는 뜻이므로, 유형별로 정밀도와 심각도 분포를 같이 본다.
    per_type: dict[str, dict] = {}
    for r in rows:
        for correct, suspicion, severity in r["verdicts_by_rank"]:
            d = per_type.setdefault(suspicion, {"tp": 0, "n": 0, "sev": 0.0})
            d["n"] += 1
            d["sev"] += severity
            if correct:
                d["tp"] += 1
    print(f"\n{'의심유형':<16} {'건수':>6} {'정밀도':>8} {'평균심각도':>10}")
    print("-" * 46)
    type_stats = {}
    for name, d in sorted(per_type.items(), key=lambda kv: -kv[1]["sev"] / max(kv[1]["n"], 1)):
        prec = d["tp"] / d["n"] if d["n"] else 0.0
        mean_sev = d["sev"] / d["n"] if d["n"] else 0.0
        type_stats[name] = {"count": d["n"], "precision": round(prec, 4),
                            "mean_severity": round(mean_sev, 4)}
        print(f"{name:<16} {d['n']:>6} {prec * 100:>7.1f}% {mean_sev:>10.3f}")

    summary = {
        "micro_precision": round(micro_p, 4),
        "micro_recall": round(micro_r, 4),
        "micro_f1": round(micro_f1, 4),
        "tp": tp, "fp": fp, "injected": injected, "caught": caught,
        "precision_at_k": pak,
        "per_suspicion_type": type_stats,
        # verdicts_by_rank는 조건당 수백 건이라 JSON에서는 뺀다 (표에 이미 요약됨)
        "per_condition": [{k: v for k, v in r.items() if k != "verdicts_by_rank"} for r in rows],
    }
    json_path = config.EXPERIMENT_ROOT / "box_accuracy_eval.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "box_accuracy_eval.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["condition", "type", "magnitude", "injected", "flagged", "tp", "fp",
              "caught", "fn", "precision", "recall", "f1", "type_accuracy"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"저장 → {json_path}\n저장 → {csv_path}")


if __name__ == "__main__":
    main()
