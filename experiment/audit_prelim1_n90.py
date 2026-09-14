"""prelim1 N=90 산술 감사 — 제품 집계 함수를 쓰지 않고 다시 센다.

**두 번째 통계 분석이 아니다.** 얼린 기존 라벨 층 내보내기에서 두 방법의 상위 90건,
겹침, 판정, 고유 오류, 보류를 집합·개수만으로 다시 세어 제품 집계
(`summary.summarise`)의 숫자와 맞는지 본다. `evaluation` 패키지를 import하지 않는다.

순위 규칙은 평가 규약 5절을 여기서 따로 옮겨 적었다: 점수 내림차순, 같으면
이미지 이름, 그다음 후보 id. 내보내기의 `severity`는 "클수록 먼저"인 순서 값이다
(AIDA는 `−rank`, 기준선은 `1 − label_iou`).

    ./venv/Scripts/python.exe audit_prelim1_n90.py

후보별 명세는 보호 폴더(`.../audit/`)에만 쓰고, 저장소에는 개수와 해시만 남긴다.
"""
import hashlib
import json
import pathlib
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

BASE = pathlib.Path("D:/AIDA-eval/prelim/prelim1_30512dfcbfbb")
EXPORT = BASE / "results" / "export_labelled.json"
PRODUCTION = pathlib.Path(__file__).resolve().parent / "planning_evidence" / "prelim1_results.json"
OUT_DETAIL = BASE / "audit" / "n90_candidates.json"
OUT_SUMMARY = pathlib.Path(__file__).resolve().parent / "planning_evidence" / "prelim1_n90_independent_audit.json"
N = 90


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top(ranks: dict[str, float], facts: dict[str, dict], n: int) -> list[str]:
    ordered = sorted(ranks, key=lambda cid: (-ranks[cid], facts[cid]["image"], cid))
    return ordered[:n]


def tally(ids: list[str], facts: dict[str, dict]) -> dict:
    verdicts = Counter(facts[c]["verdict"] for c in ids)
    hits = [c for c in ids if facts[c]["verdict"] == "hit"]
    unique = {facts[c]["unique_error_id"] for c in hits}
    return {
        "candidates": len(ids),
        "unjudged": verdicts.get(None, 0),
        "hit_candidates": len(hits),
        "unique_errors": len(unique),
        "miss": verdicts.get("miss", 0),
        "hold": verdicts.get("hold", 0),
        "decided": len(hits) + verdicts.get("miss", 0),
        "images": len({facts[c]["image"] for c in ids}),
    }


def main() -> int:
    data = json.loads(EXPORT.read_text(encoding="utf-8"))
    assert data["requested_scope"] == "labelled_candidates"
    facts = {a["canonical_candidate_id"]: a for a in data["adjudications"]}
    ranks: dict[str, dict[str, float]] = {"aida": {}, "iou_baseline": {}}
    for r in data["rankings"]:
        ranks[r["method"]][r["canonical_candidate_id"]] = float(r["severity"])
    assert set(ranks["aida"]) == set(ranks["iou_baseline"]) == set(facts), "두 방법의 후보 집합이 다르다"

    top_a = top(ranks["aida"], facts, N)
    top_b = top(ranks["iou_baseline"], facts, N)
    inter, only_a, only_b = set(top_a) & set(top_b), set(top_a) - set(top_b), set(top_b) - set(top_a)
    union = set(top_a) | set(top_b)

    def tie_at_boundary(method: str) -> dict:
        ordered = sorted(ranks[method], key=lambda c: (-ranks[method][c], facts[c]["image"], c))
        v90, v91 = ranks[method][ordered[N - 1]], ranks[method][ordered[N]]
        tied = [c for c in ordered if ranks[method][c] == v90]
        return {"value_at_90": v90, "value_at_91": v91, "tied_with_90th": len(tied),
                "boundary_split_by_tie_rule": v90 == v91}

    hits_union = [c for c in union if facts[c]["verdict"] == "hit"]
    by_error = Counter(facts[c]["unique_error_id"] for c in hits_union)

    summary = {
        "name": "prelim1_n90_independent_audit",
        "purpose": "산술 검증. 제품 집계·부트스트랩 함수를 쓰지 않았다. 두 번째 통계 분석이 아니다.",
        "input": {"export_labelled.json": sha(EXPORT)},
        "tie_rule": "점수 내림차순 → 이미지 이름 → 후보 id (평가 규약 5절)",
        "n": N,
        "aida_top90": tally(top_a, facts),
        "iou_baseline_top90": tally(top_b, facts),
        "overlap": tally(sorted(inter), facts),
        "aida_only": tally(sorted(only_a), facts),
        "baseline_only": tally(sorted(only_b), facts),
        "union": tally(sorted(union), facts),
        "difference_unique_errors": tally(top_a, facts)["unique_errors"] - tally(top_b, facts)["unique_errors"],
        "difference_hit_candidates": tally(top_a, facts)["hit_candidates"] - tally(top_b, facts)["hit_candidates"],
        "ties": {"aida": tie_at_boundary("aida"), "iou_baseline": tie_at_boundary("iou_baseline")},
        "duplicate_candidates_per_unique_error_in_union": dict(Counter(by_error.values())),
        "union_images_with_hits": len({facts[c]["image"] for c in hits_union}),
    }

    # ── 손으로 확인한 숫자와 맞는가 (docs/prelim1-results.md) ─────────────────
    assert summary["aida_top90"]["unjudged"] == 0 and summary["iou_baseline_top90"]["unjudged"] == 0
    assert summary["aida_top90"]["unique_errors"] == 4
    assert summary["iou_baseline_top90"]["unique_errors"] == 14
    assert summary["overlap"]["candidates"] == 18
    assert summary["union"]["candidates"] == 162

    # ── 제품 집계와 대조 ─────────────────────────────────────────────────────
    production = json.loads(PRODUCTION.read_text(encoding="utf-8"))
    row90 = next(r for r in production["labelled_layer"]["by_budget"] if r["budget"] == N)
    checks = {}
    for mine, theirs in (("aida_top90", "aida"), ("iou_baseline_top90", "iou_baseline")):
        for key in ("unique_errors", "hit_candidates", "holds", "decided"):
            got = summary[mine]["hold" if key == "holds" else key]
            checks[f"{theirs}.{key}"] = {"independent": got, "production": row90[theirs][key],
                                         "match": got == row90[theirs][key]}
    checks["difference_unique_errors"] = {"independent": summary["difference_unique_errors"],
                                          "production": row90["difference_unique_errors"],
                                          "match": summary["difference_unique_errors"] == row90["difference_unique_errors"]}
    summary["production_comparison"] = {"production_file_sha256": sha(PRODUCTION), "checks": checks,
                                        "all_match": all(c["match"] for c in checks.values())}

    detail = {"aida_top90": top_a, "iou_baseline_top90": top_b,
              "candidates": {c: {k: facts[c][k] for k in ("image", "label_index", "suspicion", "verdict", "unique_error_id")}
                             | {"aida_order_value": ranks["aida"][c], "baseline_score": ranks["iou_baseline"][c],
                                "in_aida_top90": c in set(top_a), "in_baseline_top90": c in set(top_b)}
                             for c in sorted(union)}}
    OUT_DETAIL.parent.mkdir(parents=True, exist_ok=True)
    if OUT_DETAIL.exists() or OUT_SUMMARY.exists():
        raise SystemExit("감사 산출물이 이미 있다 — 덮어쓰지 않는다")
    detail_text = json.dumps(detail, ensure_ascii=False, indent=2) + "\n"
    OUT_DETAIL.write_text(detail_text, encoding="utf-8")
    summary["detail_file"] = str(OUT_DETAIL).replace("\\", "/")
    summary["detail_sha256"] = hashlib.sha256(detail_text.encode("utf-8")).hexdigest()
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("aida_top90", "iou_baseline_top90", "overlap", "aida_only",
                                              "baseline_only", "ties", "duplicate_candidates_per_unique_error_in_union")},
                     ensure_ascii=False, indent=1))
    print("production all_match:", summary["production_comparison"]["all_match"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
