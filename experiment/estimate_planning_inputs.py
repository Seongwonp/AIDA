"""개발 데이터에서 계획 입력을 **어디까지** 추정할 수 있는가 (docs/planning-assumption-evidence.md).

검정력 시뮬레이션의 입력 중 "현실에 대한 가정"(오류 비율·순위 품질·묶임·중복)은
사용자가 고르는 값이 아니다. 그래서 이미 있는 개발 증거에서 무엇이 나오고 무엇이
안 나오는지를 **그대로** 적는다.

## 쓰는 자료

`box_accuracy_verdicts*.json` — `evaluate_box_accuracy.py`가 남긴 채점 캐시다.
오류를 **주입한** KITTI 조건에서, AIDA가 지목한 후보마다 한 줄:

    (정답 여부, 의심 유형, severity, 대표유형 일치, raw_signal, confidence, class_id)

정답은 `conditions/<조건>/injection_record.json` — **주입한 정답**이다. 자연 오류가
아니고, 사람이 판정한 것도 아니다. 캐시는 `.gitignore` 대상이라 이 기계에만 있다.
그래서 입력마다 SHA-256과 수정 시각을 남긴다.

## 여기서 나오는 것

- **AIDA 순위의 짝 비교 확률(AUC)** — **조건 하나 안에서**, 정답 후보가 오답 후보보다
  목록 위에 있을 확률. **AIDA가 지목한 후보 집합 안에서**의 값이다(못 잡은 주입
  오류는 후보가 아니므로 빠진다). 평가 규약의 "같은 후보 집합 안 재정렬"과 같은
  조건이다.
- 클래스별 AUC — 역시 **조건 안에서** 클래스마다 내고, 조건 사이 분포만 적는다.

## 조건을 건너 합치지 않는다

주입 조건마다 오류 유형·비율이 다르다. 예를 들어 `missing_*` 조건의 기존 라벨 후보는
**구조상 전부 오답**이다(지운 박스는 누락 후보로만 맞힐 수 있다). 조건을 합친 hit
비율이나 AUC는 "주입 설계"를 재는 숫자가 되므로 내지 않는다.

**구성끼리도 합치지 않는다.** 단일 클래스·다중 클래스·프레임 선택·자(ruler)가 다르면
다른 측정이다. 파일 하나가 한 구성이다.

## 여기서 안 나오는 것 — 지어내지 않는다

- **IoU 기준선의 AUC** — 캐시에 `label_iou`가 없다. `raw_signal`은 의심 유형별
  기하 편차라 `1 − label_iou`가 아니다. 대신 쓰지 않는다. 얻으려면 조건마다 모델
  추론을 다시 돌려야 한다(GPU).
- **이미지당 후보 수, 한 오류를 가리키는 후보 수** — 캐시에 이미지·라벨 번호가 없다.
- **자연 오류 비율** — 주입 조건은 오류를 일부러 넣은 데이터다.

    ./venv/Scripts/python.exe estimate_planning_inputs.py --out planning_evidence/development_ranking_estimates.json
"""
import argparse
import datetime
import hashlib
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# 기존 라벨 층만 본다. 누락 후보는 비교 층이 아니다(평가 규약 2-1절).
MISSING = "missing"
# 클래스별 AUC를 낼 최소 표본 (조건 하나 안에서 정답·오답 각각). **근거가 약한
# 운영 기준이다** — 몇 쌍만으로 낸 AUC는 0이나 1로 튄다.
MIN_PER_SIDE = 10

# 파일 꼬리표의 뜻. `evaluate_box_accuracy._tag()`와 `config._csuffix`에서 읽었다.
CONFIGURATION = {
    "": {"classes": "Car (단일 클래스)", "frames": "기본", "ruler": "같은 구성의 clean 자",
         "use_for_planning": "제한적 — 캐시에 조건 1개(width_m30)만 남아 있다"},
    "_mc": {"classes": "Car·Van·Pedestrian·Cyclist", "frames": "기본", "ruler": "같은 구성의 clean 자",
            "use_for_planning": "참고 가능 — 제품과 같은 구성의 자"},
    "_mc_cyclist_rich": {"classes": "Car·Van·Pedestrian·Cyclist", "frames": "cyclist_rich",
                         "ruler": "같은 구성의 clean 자",
                         "use_for_planning": "참고 가능 — 제품과 같은 구성의 자"},
    "_mc_cyclist_rich_ruler_runs": {"classes": "Car·Van·Pedestrian·Cyclist", "frames": "cyclist_rich",
                                    "ruler": "runs/ 의 자(단일 클래스 Car)",
                                    "use_for_planning": "쓰지 않는다 — 자와 데이터의 클래스 구성이 다르다"},
    "_mc_cyclist_rich_ruler_runs_mc": {"classes": "Car·Van·Pedestrian·Cyclist", "frames": "cyclist_rich",
                                       "ruler": "runs_mc/ 의 자(다른 프레임으로 학습한 4클래스)",
                                       "use_for_planning": "도메인 이동 참고 — 자를 다른 장면에서 학습"},
    "_mc_cyclist_rich_ruler_runs_mc_broad_n800": {"classes": "Car·Van·Pedestrian·Cyclist",
                                                  "frames": "cyclist_rich",
                                                  "ruler": "runs_mc_broad_n800/ 의 자(broad 800장)",
                                                  "use_for_planning": "도메인 이동 참고"},
    "_mc_ruler_self": {"classes": "Car·Van·Pedestrian·Cyclist", "frames": "기본",
                       "ruler": "조건 자신의 데이터로 학습한 자(오염된 자)",
                       "use_for_planning": "쓰지 않는다 — 오류가 섞인 데이터로 학습한 자"},
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def auc_from_order(correct_in_order: list[bool]) -> float | None:
    """목록 순서만으로 낸 짝 비교 확률. 정답이 오답보다 **위에** 있을 확률.

    위치는 겹치지 않으므로 동점이 없다. 정답이나 오답이 하나도 없으면 말할 수 없다.
    """
    n_true = sum(bool(x) for x in correct_in_order)
    n_false = len(correct_in_order) - n_true
    if n_true == 0 or n_false == 0:
        return None
    falses_below = 0
    wins = 0
    for is_true in reversed(correct_in_order):      # 아래부터 올라가며 센다
        if is_true:
            wins += falses_below
        else:
            falses_below += 1
    return wins / (n_true * n_false)


def auc_from_scores(pairs: list[tuple[bool, float]]) -> float | None:
    """점수로 낸 짝 비교 확률. 동점은 0.5로 센다 (Mann–Whitney)."""
    trues = [s for c, s in pairs if c]
    falses = [s for c, s in pairs if not c]
    if not trues or not falses:
        return None
    wins = 0.0
    for t in trues:
        for f in falses:
            wins += 1.0 if t > f else 0.5 if t == f else 0.0
    return wins / (len(trues) * len(falses))


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    """이항 비율의 95% Wilson 구간. k=0이나 k=n에서도 폭이 0이 되지 않는다."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def spread(values: list[float]) -> dict | None:
    if not values:
        return None
    v = sorted(values)
    mid = len(v) // 2
    median = v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2
    return {"n": len(v), "min": round(v[0], 4), "median": round(median, 4), "max": round(v[-1], 4)}


def condition_summary(rows: list[list]) -> dict:
    """조건 하나. **기존 라벨 층만.**"""
    labelled = [r for r in rows if r[1] != MISSING]
    order = [bool(r[0]) for r in labelled]
    k, n = sum(order), len(order)
    return {
        "labelled_candidates": n,
        "injected_true": k,
        "hit_rate_against_injected_truth": None if n == 0 else round(k / n, 4),
        "hit_rate_wilson95": None if n == 0 else [round(x, 4) for x in wilson(k, n)],
        "aida_auc_by_review_order": _r(auc_from_order(order)),
        "aida_auc_by_severity": _r(auc_from_scores([(bool(r[0]), float(r[2])) for r in labelled])),
        "missing_candidates_excluded": len(rows) - n,
    }


def _r(x):
    return None if x is None else round(x, 4)


def nearest_commit_before(path: Path) -> str | None:
    """파일 수정 시각 직전의 커밋. **추정이다** — 캐시를 만든 작업 트리가 커밋과
    같았는지는 알 수 없다."""
    when = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    got = subprocess.run(["git", "-C", str(REPO), "log", "-1", f"--before={when}", "--format=%h"],
                         capture_output=True, text=True, encoding="utf-8")
    return got.stdout.strip() or None


def analyse_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    tag = path.stem.replace("box_accuracy_verdicts", "")
    per_condition = {}
    auc_order, auc_severity = [], []
    class_auc: dict[str, list[float]] = defaultdict(list)
    for name, cond in data.items():
        rows = cond["verdicts_by_rank"]
        summary = condition_summary(rows)
        per_condition[name] = {"injected_type": cond.get("type"),
                               "magnitude": cond.get("magnitude"), **summary}
        if summary["aida_auc_by_review_order"] is not None:
            auc_order.append(summary["aida_auc_by_review_order"])
        if summary["aida_auc_by_severity"] is not None:
            auc_severity.append(summary["aida_auc_by_severity"])
        # 클래스별 — 조건 **안에서** 목록 순서를 유지한 채 그 클래스 후보만 본다.
        by_class: dict[str, list[bool]] = defaultdict(list)
        for r in rows:
            if r[1] != MISSING and len(r) > 6 and r[6] is not None:
                by_class[str(r[6])].append(bool(r[0]))
        for cid, order in by_class.items():
            t = sum(order)
            if t >= MIN_PER_SIDE and len(order) - t >= MIN_PER_SIDE:
                class_auc[cid].append(auc_from_order(order))

    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes")
    return {
        "file": path.name,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "modified": mtime,
        "nearest_commit_before_modified": nearest_commit_before(path),
        "configuration_tag": tag or "(없음)",
        "configuration": CONFIGURATION.get(tag, {"use_for_planning": "모르는 구성 — 쓰지 않는다"}),
        "truth": "injected",
        "dataset": "KITTI (개발)",
        "conditions": len(data),
        # **조건을 합친 AUC는 내지 않는다.** 조건별 값의 분포만 적는다.
        "aida_auc_by_review_order_across_conditions": spread(auc_order),
        "aida_auc_by_severity_across_conditions": spread(auc_severity),
        "class_id_order": "config.CLASS_NAMES 순서 (4클래스면 0=Car, 1=Van, 2=Pedestrian, 3=Cyclist)",
        "aida_auc_by_class_within_condition": {
            cid: spread(v) for cid, v in sorted(class_auc.items())},
        "class_auc_min_per_side": MIN_PER_SIDE,
        "per_condition": per_condition,
    }


NOT_ESTIMABLE = {
    "baseline_iou_auc": ("캐시에 label_iou가 없다. raw_signal은 유형별 기하 편차라 1 − label_iou가 "
                         "아니므로 대신 쓰지 않는다. 조건마다 모델 추론을 다시 돌려야 얻는다(GPU)."),
    "aida_minus_baseline_auc_gap": "기준선 AUC가 없으므로 검정력을 좌우하는 두 방법의 차이도 없다.",
    "candidates_per_image": "캐시에 이미지 번호가 없다.",
    "duplicate_candidates_per_unique_error": "캐시에 라벨 번호가 없어 같은 주입 오류를 가리키는 후보를 묶을 수 없다.",
    "natural_error_prevalence": "주입 조건은 오류를 일부러 넣은 데이터라 자연 오류 비율이 아니다.",
    "adjudication_error": "주입 정답이라 사람 판정 오류가 없다. 사람 판정 오류는 외부 판정자 없이 알 수 없다.",
}


def build_report(files: list[Path]) -> dict:
    return {
        "generator": "experiment/estimate_planning_inputs.py",
        "truth": "injected (conditions/<condition>/injection_record.json)",
        "scope": "KITTI 개발 데이터, 주입 오류 조건. 자연 오류 추정이 아니다.",
        "layer": "기존 라벨 층(누락 후보 제외)",
        "candidate_set": "AIDA가 지목한 후보만 — 못 잡은 주입 오류는 포함되지 않는다",
        "pooling": "조건·구성을 건너 합치지 않는다",
        "files": [analyse_file(f) for f in files],
        "not_estimable_from_these_inputs": NOT_ESTIMABLE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="개발 증거에서 계획 입력 추정")
    parser.add_argument("--out", required=True, help="JSON 저장 경로")
    args = parser.parse_args()

    files = sorted(HERE.glob("box_accuracy_verdicts*.json"))
    if not files:
        print("box_accuracy_verdicts*.json이 없다 — 이 기계에만 있는 채점 캐시다(.gitignore).")
        return 1
    report = build_report(files)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    for f in report["files"]:
        s = f["aida_auc_by_review_order_across_conditions"]
        use = f["configuration"].get("use_for_planning", "")
        print(f"{f['file']}: 조건 {f['conditions']}, AIDA AUC(조건별, 목록 순서) "
              + (f"{s['min']}~{s['max']} 중앙 {s['median']} (n={s['n']})" if s else "없음")
              + f" | {use}")
    print(f"저장: {out}  sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
