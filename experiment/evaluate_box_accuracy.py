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
from label_diagnosis import (CLASS_VULNERABILITY, iou, present_types, rescore,
                             severity_for, summarize)

# 누락 의심 예측 박스가 "지워진 그 박스"를 가리키는 것으로 인정할 최소 IoU.
# 위치가 이 정도로 겹치면 같은 객체를 지목했다고 본다.
MISSING_MATCH_IOU = 0.4

# 프로파일에 쓸 최소 표본 수. 이보다 적으면 그 유형은 기본값을 유지한다 —
# J에서 누락의 부재 시 신뢰도를 n=17로 정했다가 근거가 얇다고 적어둔 일이 있다.
MIN_PROFILE_SAMPLES = 30
# 프로파일 값 상한. 표본 수백 건에서 정밀도 100%가 나와도 "이 유형은 절대
# 틀리지 않는다"로 굳히지는 않는다. 순서는 그대로 두면서 여지를 남긴다.
MAX_PROFILE_RELIABILITY = 0.99


def _tag() -> str:
    """결과 파일 이름에 붙일 꼬리표. 클래스 구성 + 자로 쓴 모델.

    자를 바꾸면 완전히 다른 측정이다. 꼬리표를 안 붙이면 self 실행이
    clean 결과를 덮어쓴다 — 오늘만 세 번 겪은 종류의 사고다.
    """
    return config._csuffix + ("" if RULER == "clean" else f"_ruler_{RULER}")


def verdict_cache() -> Path:
    return config.EXPERIMENT_ROOT / f"box_accuracy_verdicts{_tag()}.json"


def _verdict(correct: bool, finding, predicted_dominant: str | None) -> tuple:
    """채점 결과 한 건. severity와 함께 raw_signal도 남기는 게 핵심이다 —
    TP/FP 판정은 severity와 무관하므로, 원시 신호만 있으면 심각도 공식을
    바꿔도 추론을 다시 돌리지 않고 순위를 재계산할 수 있다(--reuse-cache).
    """
    return (correct, finding.suspicion, finding.severity,
            finding.suspicion == predicted_dominant, finding.raw_signal,
            finding.confidence, finding.class_id)


def load_injection_record(condition_name: str) -> dict:
    path = config.CONDITIONS_DIR / condition_name / "injection_record.json"
    if not path.exists():
        raise RuntimeError(
            f"{path} 없음 — error_injector.py를 다시 실행해 정답지를 생성하세요"
        )
    return json.loads(path.read_text(encoding="utf-8"))


# 진단이 자로 쓸 모델을 무엇으로 할지. main()이 인자를 보고 정한다.
#   clean  오류 없는 라벨로 학습한 모델 (지금까지의 모든 측정이 이 전제)
#   self   그 조건 자신의 라벨로 학습한 모델 = 고객이 자기 오류 데이터로
#          학습한 모델. 깨끗한 기준이 없는 현실을 흉내 낸다.
RULER = "clean"


def ruler_for(condition: config.Condition):
    """이 조건을 진단할 때 자로 쓸 가중치 경로."""
    if RULER == "self":
        return config.RUNS_DIR / condition.name / "weights" / "best.pt"
    return None  # diagnose_labels가 CLEAN_WEIGHTS로 넘어간다


def score_condition(condition: config.Condition, limit: int | None) -> dict:
    """조건 하나에 대해 박스 단위 TP/FP/FN을 센다."""
    from diagnose_labels import run  # 지연 import — GPU 없는 환경에서도 모듈 로드는 되게

    root = config.CONDITIONS_DIR / condition.name
    images_dir, labels_dir = root / "images" / "train", root / "labels" / "train"
    findings, total_labels = run(images_dir, labels_dir, limit, weights=ruler_for(condition))
    record = load_injection_record(condition.name)

    # 진단이 스스로 예측한 대표 유형 — 신뢰도 보정 기준은 정답(주입 유형)이
    # 아니라 이 예측값이어야 한다. 런타임에는 정답을 모르므로, 정답으로
    # 보정하면 실제보다 낙관적인 상수가 나온다(docs/21 F 계획 1단계 참고).
    summary = summarize(findings, total_labels)
    predicted_dominant = summary["dominant_type"] if summary["systematic"] else None
    # 제품과 같은 2패스를 거쳐야 실제로 고객이 보는 순서를 평가하게 된다
    findings = rescore(findings, summary)

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
    # (정답여부, 의심유형, 심각도, 예측대표유형과일치, 원시신호)
    verdicts_by_rank: list[tuple] = []

    findings = sorted(findings, key=_sort_key)
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
                verdicts_by_rank.append(_verdict(True, f, predicted_dominant))
            else:
                fp += 1
                verdicts_by_rank.append(_verdict(False, f, predicted_dominant))
        else:
            hit = _errored_index_for(condition.type, f.label_index, entry["errored"])
            if hit is not None:
                tp += 1
                matched_errored.add((stem, hit))
                if _type_matches(condition.type, f.suspicion):
                    type_correct += 1
                verdicts_by_rank.append(_verdict(True, f, predicted_dominant))
            else:
                fp += 1
                verdicts_by_rank.append(_verdict(False, f, predicted_dominant))

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
        "predicted_dominant": predicted_dominant,
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
        # 캐시로 순위를 다시 매길 때 필요하다 — 이게 없으면 어떤 유형이
        # 승격 대상이었는지 복원할 수 없다.
        "present_types": sorted(present_types(summary)),
        "verdicts_by_rank": verdicts_by_rank,
    }


def load_cached_rows(wanted: list[str]) -> list[dict]:
    """지난 실행의 채점 기록으로 조건별 결과를 복원하고 심각도만 다시 매긴다.

    TP/FP 판정은 심각도와 무관하다 — 어느 박스를 지목했고 그게 맞았는지는
    이미 정해져 있고, 심각도는 그걸 어떤 순서로 보여줄지만 정한다. 그래서
    원시 신호와 확신도만 남아 있으면 추론(조건당 수 분)을 건너뛸 수 있다.
    """
    cache = verdict_cache()
    if not cache.exists():
        raise SystemExit(f"{cache} 없음 — --reuse-cache 전에 한 번은 돌려야 합니다")
    cached = json.loads(cache.read_text(encoding="utf-8"))
    missing = set(wanted) - set(cached)
    if missing:
        raise SystemExit(f"캐시에 없는 조건: {sorted(missing)} — 이 조건들을 먼저 돌리세요")

    rows = []
    # 정식 실행과 같은 순서로 — 출력이 한 글자도 다르지 않아야 캐시 결과를
    # 믿고 쓸 수 있다
    for name in wanted:
        row = dict(cached[name])
        present = set(row.get("present_types", []))
        rescored = []
        for v in row["verdicts_by_rank"]:
            correct, suspicion, _old_sev, is_dominant, raw, conf = v[:6]
            cid = v[6] if len(v) > 6 else None   # 옛 캐시에는 클래스가 없다
            sev = severity_for(suspicion, raw, is_present=suspicion in present,
                               confidence=conf)
            rescored.append((correct, suspicion, sev, is_dominant, raw, conf, cid))

        def order(x):
            if CLASS_WEIGHTED and CLASS_VULNERABILITY and x[6] is not None:
                return -(x[2] * CLASS_VULNERABILITY.get(x[6], 1.0))
            return -x[2]

        row["verdicts_by_rank"] = sorted(rescored, key=order)
        rows.append(row)
    return rows


# 클래스 가중 정렬을 켤지. main()이 인자를 보고 정한다.
CLASS_WEIGHTED = False


def _sort_key(f):
    from label_diagnosis import review_value
    return -(review_value(f) if CLASS_WEIGHTED else f.severity)


def recovered_at_k(verdicts: list[tuple], k: int) -> float:
    """상위 k건을 고쳤을 때 되찾는 피해의 비율.

    precision@k는 "지목한 것 중 몇 개가 맞았나"만 본다. 그런데 실측상 같은
    오류라도 클래스마다 성능 피해가 20배 가까이 다르다(Car 3.4% vs Cyclist
    27.4%, docs/21 Q). 맞은 개수가 같아도 어느 클래스를 맞혔느냐에 따라
    검수의 값어치가 달라진다는 뜻이다.

    그래서 TP를 그 클래스의 취약도로 가중해, **전체 고칠 수 있는 피해 중
    상위 k에서 얼마나 건지는가**를 잰다. 취약도 정보가 없으면 모든 클래스가
    1.0이라 precision@k의 재현율 버전이 된다.
    """
    def weight(v: tuple) -> float:
        cid = v[6] if len(v) > 6 else None
        if not CLASS_VULNERABILITY or cid is None:
            return 1.0
        return CLASS_VULNERABILITY.get(cid, 1.0)

    total = sum(weight(v) for v in verdicts if v[0])
    if total <= 0:
        return 0.0
    return sum(weight(v) for v in verdicts[:k] if v[0]) / total


def precision_at_k(verdicts: list[tuple], k: int) -> float:
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
    if condition_type == "class_swap":
        return suspicion == "class_mismatch"
    return condition_type == suspicion


def main():
    parser = argparse.ArgumentParser(description="박스 단위 진단 정확도 평가")
    parser.add_argument("--limit", type=int, default=80, help="조건당 이미지 수")
    parser.add_argument("--conditions", nargs="+", help="특정 조건만")
    parser.add_argument("--ruler", choices=["clean", "self"], default="clean",
                        help="진단이 자로 쓸 모델. self는 그 조건 자신의 라벨로 "
                             "학습한 모델을 쓴다 — 깨끗한 기준 모델이 없는 "
                             "고객 상황을 흉내 낸다")
    parser.add_argument("--class-weighted", action="store_true",
                        help="심각도에 클래스 취약도를 곱해 정렬한다. 목록의 "
                             "정밀도 대신 '되찾는 성능'을 최대화하는 정렬이라 "
                             "지표가 서로 반대로 움직일 수 있다.")
    parser.add_argument("--reuse-cache", action="store_true",
                        help="추론을 다시 돌리지 않고 지난 채점 기록으로 순위만 "
                             "다시 계산한다 (심각도 공식·신뢰도 상수 조정용). "
                             "TP/FP 판정은 심각도와 무관하므로 그대로 쓴다.")
    parser.add_argument("--write-profile", metavar="PATH",
                        help="실측한 유형 신뢰도를 프로파일 JSON으로 저장 "
                             "(AIDA_RELIABILITY_PROFILE로 지정해 쓰면 됨)")
    args = parser.parse_args()

    global CLASS_WEIGHTED, RULER
    CLASS_WEIGHTED = args.class_weighted
    RULER = args.ruler
    if CLASS_WEIGHTED and not CLASS_VULNERABILITY:
        raise SystemExit("클래스 취약도가 없습니다 — build_class_vulnerability.py로 "
                         "프로파일에 넣고 AIDA_RELIABILITY_PROFILE로 지정하세요")

    conditions = [c for c in config.conditions_in_run_order() if c.type != "none"]
    if args.conditions:
        by_name = {c.name: c for c in config.CONDITIONS + config.CLASS_SWAP_CONDITIONS
                   + config.REVIEW_SIM_CONDITIONS}
        conditions = [by_name[n] for n in args.conditions]

    if args.reuse_cache:
        rows = load_cached_rows([c.name for c in conditions])
        print(f"캐시에서 {len(rows)}개 조건을 읽어 심각도만 다시 계산합니다 "
              f"({verdict_cache().name})")
    else:
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
        rec = [recovered_at_k(r["verdicts_by_rank"],
                              max(1, int(len(r["verdicts_by_rank"]) * frac)))
               for r in rows]
        rec_avg = sum(rec) / len(rec) if rec else 0.0
        pak[f"recovered_top_{int(frac * 100)}pct"] = round(rec_avg, 4)
        print(f"  상위 {int(frac * 100):>3}%: 정밀도 {avg * 100:5.1f}%   "
              f"피해 회수 {rec_avg * 100:5.1f}%")

    # 유형별 신뢰도 — 상위권 정밀도가 낮다면 "심각도 높은 유형이 실은 덜
    # 미덥다"는 뜻이므로, 유형별로 정밀도와 심각도 분포를 같이 본다.
    per_type: dict[str, dict] = {}
    for r in rows:
        for v in r["verdicts_by_rank"]:
            correct, suspicion, severity = v[0], v[1], v[2]
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

    # F 계획 1단계: 유형 신뢰도를 "그 유형이 데이터셋의 예측 대표 유형인가"로
    # 나눠서 잰다. 전역 상수가 낮은 이유가 "그 유형이 원래 안 미더워서"인지
    # "그 유형이 없는 데이터셋까지 섞여서"인지 여기서 갈린다.
    split: dict[str, dict] = {}
    for r in rows:
        for v in r["verdicts_by_rank"]:
            correct, suspicion, is_dominant = v[0], v[1], v[3]
            bucket = split.setdefault(suspicion, {
                "matched": [0, 0], "unmatched": [0, 0],  # [tp, n]
            })
            key = "matched" if is_dominant else "unmatched"
            bucket[key][1] += 1
            if correct:
                bucket[key][0] += 1

    print(f"\n{'의심유형':<16} {'대표유형일때':>20} {'아닐때':>18}")
    print("-" * 58)
    conditional = {}
    for name in sorted(split, key=lambda n: -split[n]["matched"][1]):
        m_tp, m_n = split[name]["matched"]
        u_tp, u_n = split[name]["unmatched"]
        m_p = m_tp / m_n if m_n else None
        u_p = u_tp / u_n if u_n else None
        conditional[name] = {
            "matched_precision": round(m_p, 4) if m_p is not None else None,
            "matched_n": m_n,
            "unmatched_precision": round(u_p, 4) if u_p is not None else None,
            "unmatched_n": u_n,
        }
        m_s = f"{m_p * 100:5.1f}% (n={m_n})" if m_p is not None else f"    -  (n={m_n})"
        u_s = f"{u_p * 100:5.1f}% (n={u_n})" if u_p is not None else f"    -  (n={u_n})"
        print(f"{name:<16} {m_s:>20} {u_s:>18}")

    summary = {
        "micro_precision": round(micro_p, 4),
        "micro_recall": round(micro_r, 4),
        "micro_f1": round(micro_f1, 4),
        "tp": tp, "fp": fp, "injected": injected, "caught": caught,
        "precision_at_k": pak,
        "per_suspicion_type": type_stats,
        "conditional_reliability": conditional,
        # verdicts_by_rank는 조건당 수백 건이라 JSON에서는 뺀다 (표에 이미 요약됨)
        "per_condition": [{k: v for k, v in r.items() if k != "verdicts_by_rank"} for r in rows],
    }
    # 캐시에는 순위를 다시 매기는 데 필요한 것을 전부 담는다. verdicts만
    # 담으면 severity 공식을 바꿔도 is_present를 복원할 수 없어서 재계산이
    # 불가능하다 — 실제로 그래서 --reuse-cache가 문서에만 있고 없었다.
    verdict_cache().write_text(json.dumps(
        {r["condition"]: {k: v for k, v in r.items()} for r in rows},
        ensure_ascii=False,
    ), encoding="utf-8")

    if args.write_profile:
        # 방금 실측한 값을 그대로 신뢰도 프로파일로 떨군다. 표본이 너무 적은
        # 유형은 뺀다 — 근거 없는 상수를 프로파일에 굳히면 기본값보다 나쁘다.
        # 클래스 구성을 함께 적는다. 신뢰도 상수만 갈아끼우고 모델·라벨 구성은
        # 그대로면 반쪽짜리다 — 그 상수는 이 클래스 구성에서 잰 값이므로
        # 프로파일을 쓰는 쪽이 같은 구성으로 진단해야 한다.
        profile = {"classes": config.CLASS_NAMES, "present": {}, "noise": {}}
        for name, d in conditional.items():
            if d["matched_n"] >= MIN_PROFILE_SAMPLES:
                profile["present"][name] = min(round(d["matched_precision"], 4),
                                               MAX_PROFILE_RELIABILITY)
            if d["unmatched_n"] >= MIN_PROFILE_SAMPLES:
                profile["noise"][name] = min(round(d["unmatched_precision"], 4),
                                             MAX_PROFILE_RELIABILITY)
        skipped = sorted(
            {n for n, d in conditional.items()
             if d["matched_n"] < MIN_PROFILE_SAMPLES or d["unmatched_n"] < MIN_PROFILE_SAMPLES}
        )
        out = Path(args.write_profile)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print(f"신뢰도 프로파일 저장 → {out}")
        if skipped:
            print(f"  표본 {MIN_PROFILE_SAMPLES}건 미만이라 기본값을 유지한 유형: {', '.join(skipped)}")

    # 클래스 구성이 다르면 결과도 다른 실험이다 — Car 단일 결과를 덮지 않게 분리
    json_path = config.EXPERIMENT_ROOT / f"box_accuracy_eval{_tag()}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = (config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data"
                / f"box_accuracy_eval{_tag()}.csv")
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
