"""prelim1 사후 실패 분석 — **가설을 만드는 용도, 선택 편향이 있다.**

판정된 것은 두 방법 상위 90건의 합집합(162건)뿐이다. 그 안에서 유형·계통 유형
승격·심각도·`label_iou`·순위 위치·집합(겹침/AIDA만/기준선만)별로 판정을 센다.

**하지 않는 것.**
- 판정 안 한 후보를 miss로 치지 않는다.
- 새 순위 공식을 이 데이터로 평가하지 않는다 — 새 순위의 상위에는 판정 안 한 후보가
  섞이고, 결과를 본 뒤 고른 공식은 이 데이터에 맞춰진다.
- 여러 공식을 뒤져 가장 좋은 것을 보고하지 않는다.

    ./venv/Scripts/python.exe analyze_prelim1_failure.py
"""
import hashlib
import json
import pathlib
import statistics
import sys
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from label_diagnosis import SYSTEMATIC_ERROR_RATIO, order_basis, present_types  # noqa: E402

BASE = pathlib.Path("D:/AIDA-eval/prelim/prelim1_30512dfcbfbb")
DIAG = BASE / "label_diagnosis.json"
DETAIL = BASE / "audit" / "n90_candidates.json"
OUT = pathlib.Path(__file__).resolve().parent / "planning_evidence" / "prelim1_failure_analysis.json"


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def spread(xs):
    if not xs:
        return None
    return {"n": len(xs), "min": round(min(xs), 4), "median": round(statistics.median(xs), 4),
            "max": round(max(xs), 4)}


def counts(rows):
    c = Counter(r["verdict"] for r in rows)
    return {"candidates": len(rows), "hit": c.get("hit", 0), "miss": c.get("miss", 0),
            "hold": c.get("hold", 0)}


def main() -> int:
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    detail = json.loads(DETAIL.read_text(encoding="utf-8"))
    summary = diag["summary"]
    present = present_types(summary)

    labelled = sorted((r for r in diag["all_candidates"] if r["label_index"] is not None),
                      key=lambda r: r["rank"])
    position = {(r["image"], r["label_index"], r["suspicion"]): i + 1 for i, r in enumerate(labelled)}
    by_key = {(r["image"], r["label_index"], r["suspicion"]): r for r in labelled}

    union = []
    for cid, c in detail["candidates"].items():
        key = (c["image"], c["label_index"], c["suspicion"])
        member = ("overlap" if c["in_aida_top90"] and c["in_baseline_top90"]
                  else "aida_only" if c["in_aida_top90"] else "baseline_only")
        union.append({**c, "id": cid, "set": member, "present_type": c["suspicion"] in present,
                      "severity": by_key[key]["severity"], "label_iou": by_key[key]["label_iou"],
                      "aida_labelled_position": position[key]})

    by_type = defaultdict(list)
    for r in union:
        by_type[r["suspicion"]].append(r)
    by_set = defaultdict(list)
    for r in union:
        by_set[f"{r['set']}|present_type={r['present_type']}"].append(r)

    aida_top = detail["aida_top90"]
    base_top = detail["iou_baseline_top90"]
    cand = detail["candidates"]

    result = {
        "name": "prelim1_failure_analysis",
        "label": "사후 분석 — 가설 생성용, 선택 편향 있음. 판정된 합집합 162건만 본다. 새 순위를 검증하지 않는다.",
        "inputs_sha256": {"label_diagnosis.json": sha(DIAG), "n90_candidates.json": sha(DETAIL)},
        "product_order": {
            "rule": "계통 유형(present_types)을 먼저, 그 안에서 severity 내림차순 (label_diagnosis.review_order)",
            "order_basis": order_basis(summary),
            "systematic_flag": summary.get("systematic"),
            "absolute_threshold": SYSTEMATIC_ERROR_RATIO,
            "type_ratios_among_labels": {t["suspicion"]: t["ratio"] for t in summary.get("by_type", [])},
            "present_types": sorted(present),
            "labelled_pool": len(labelled),
            "present_type_candidates": sum(r["suspicion"] in present for r in labelled),
            "first_non_present_position": next((i + 1 for i, r in enumerate(labelled)
                                                if r["suspicion"] not in present), None),
        },
        "top90_type_mix": {"aida": dict(Counter(cand[c]["suspicion"] for c in aida_top)),
                           "iou_baseline": dict(Counter(cand[c]["suspicion"] for c in base_top))},
        "judged_union_by_type": {k: counts(v) for k, v in sorted(by_type.items())},
        "judged_union_by_set_and_promotion": {k: counts(v) for k, v in sorted(by_set.items())},
        "hit_positions": {
            "aida_top90_positions": sorted(i + 1 for i, c in enumerate(aida_top) if cand[c]["verdict"] == "hit"),
            "baseline_top90_positions": sorted(i + 1 for i, c in enumerate(base_top) if cand[c]["verdict"] == "hit"),
            "baseline_only_hits_aida_labelled_positions": sorted(
                r["aida_labelled_position"] for r in union if r["set"] == "baseline_only" and r["verdict"] == "hit"),
        },
        "severity_by_verdict": {v: spread([r["severity"] for r in union if r["verdict"] == v]) for v in ("hit", "miss", "hold")},
        "label_iou_by_verdict": {v: spread([r["label_iou"] for r in union if r["verdict"] == v]) for v in ("hit", "miss", "hold")},
        "union_candidates_per_image": dict(sorted(Counter(Counter(r["image"] for r in union).values()).items())),
        "hits_per_unique_error": dict(Counter(Counter(r["unique_error_id"] for r in union if r["verdict"] == "hit").values())),
    }
    if OUT.exists():
        raise SystemExit("이미 있다 — 덮어쓰지 않는다")
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("product_order", "top90_type_mix", "judged_union_by_set_and_promotion",
                                             "severity_by_verdict", "label_iou_by_verdict")}, ensure_ascii=False, indent=1))
    print("sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
