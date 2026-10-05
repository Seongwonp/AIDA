"""통제 기준선 2단계 집계 — GPU 없음. 입력은 run_controlled_baseline_stage2.py의 조건별 기록.

명세: docs/paper/controlled-baseline-spec.md 3절. 조건마다 공통 예산
k = max(1, floor(0.1 × AIDA finding 수))를 한 번 정해 모든 방법에 쓴다. finding 0건 조건은
silent로 모든 방법에서 뺀다. 후보가 k보다 적으면 있는 만큼만 보고 분모는 k.

방법(기존 라벨 층):
  aida_legacy / aida_current   AIDA finding 순서(legacy_severity_v0 / review_order_v1), finding 단위
  aida_random_expected         AIDA finding 안 무작위의 기대값 = TP / flagged, finding 단위
  aida_iou_reorder             AIDA finding을 label_iou 오름차순으로 다시 정렬(동점: 이미지·라벨
                               인덱스·원래 순서), label_iou가 없는 finding(누락 유형)은 뒤에 AIDA 순서로.
                               finding 단위
  aida_current_unique          review_order_v1에서 같은 라벨의 두 번째 이후 finding을 건너뛴 고유 단위
  all_label_random_expected    범위 안 전체 라벨의 주입 오류 비율, 고유 라벨 단위
  all_label_iou                전체 라벨 1 − label_iou 내림차순(동점: 이미지, 라벨 인덱스), 고유 라벨 단위
  all_label_objectlab          전체 라벨 objectlab_score 오름차순(점수 있는 라벨만), 고유 라벨 단위
  all_label_iou_excl0_posthoc  (사후 보조, 명세 밖) label_iou = 0 라벨을 뺀 all_label_iou
누락 층(missing_* 조건만, 별도 예산 k_m = max(1, floor(0.1 × AIDA 누락 finding 수))):
  aida_missing, unmatched_confidence(확신도 내림차순), unmatched_objectlab(overlooked 오름차순),
  unmatched_random_expected(matches_dropped 비율).

사용법: python analyze_controlled_baseline_stage2.py [--out planning_evidence/...json]
"""
import argparse
import gzip
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "controlled_baseline_stage2"
LEG, CUR = "legacy_severity_v0", "review_order_v1"
EXISTING_METHODS = ["aida_legacy", "aida_current", "aida_random_expected", "aida_iou_reorder",
                    "aida_current_unique", "all_label_random_expected", "all_label_iou",
                    "all_label_objectlab", "all_label_iou_excl0_posthoc"]
MISSING_METHODS = ["aida_missing", "unmatched_confidence", "unmatched_objectlab",
                   "unmatched_random_expected"]
SEEDED = {"A": ("seeded_ruler4_7seeds.json", {"matched": "자기 도메인", "shifted": "약한 이동",
                                               "far": "먼 이동(1C)", "broad": "넓은 자(800)"}),
          "B": ("seeded_coco_3seeds.json", {"coco_self": "COCO 자기(1C)",
                                            "kitti_on_coco": "KITTI→COCO(1C)"})}
EVAL_REF = {"C": "box_accuracy_eval_mc_ruler_self.json", "D": "box_accuracy_eval.json"}


def p_at(flags: list[bool], k: int) -> float:
    return sum(bool(x) for x in flags[:k]) / k


def condition_metrics(rec: dict) -> dict:
    cur, leg = rec["rows"][CUR], rec["rows"][LEG]
    flagged = len(cur["verdicts_by_rank"])
    out = {"condition": rec["condition"], "flagged": flagged, "tp": cur["tp"]}
    pop = rec["population"]
    labels = pop["all_labels"]
    out["n_labels"] = len(labels)
    out["n_injected_labels"] = sum(r["injected_error"] for r in labels)
    if flagged == 0:
        out["silent"] = True
        return out
    k = max(1, int(flagged * 0.1))
    out["k"] = k
    m = {}
    m["aida_legacy"] = p_at([v[0] for v in leg["verdicts_by_rank"]], k)
    m["aida_current"] = p_at([v[0] for v in cur["verdicts_by_rank"]], k)
    m["aida_random_expected"] = cur["tp"] / flagged
    iou = {(r["image"], r["label_index"]): r["label_iou"] for r in labels}
    items = [(v[0], tuple(fid), i) for i, (v, fid) in
             enumerate(zip(cur["verdicts_by_rank"], cur["finding_ids_by_rank"]))]
    with_iou = [x for x in items if x[1] in iou]
    without = [x for x in items if x[1] not in iou]
    with_iou.sort(key=lambda x: (iou[x[1]], x[1][0], x[1][1], x[2]))
    out["aida_findings_with_label_iou"] = len(with_iou)
    m["aida_iou_reorder"] = p_at([x[0] for x in with_iou + without], k)
    seen, uniq = set(), []
    for c, fid, _ in items:
        if fid[1] is not None:
            if fid in seen:
                continue
            seen.add(fid)
        uniq.append(c)
    m["aida_current_unique"] = p_at(uniq, k)
    m["all_label_random_expected"] = (out["n_injected_labels"] / len(labels)) if labels else 0.0
    by_iou = sorted(labels, key=lambda r: (r["label_iou"], r["image"], r["label_index"]))
    m["all_label_iou"] = p_at([r["injected_error"] for r in by_iou], k)
    # 사후 보조(명세 밖): label_iou = 0(짝 예측 없음) 라벨이 상위 k를 채우는지 보려고 뺀 변형
    out["n_labels_iou0"] = sum(1 for r in labels if r["label_iou"] == 0)
    m["all_label_iou_excl0_posthoc"] = p_at(
        [r["injected_error"] for r in by_iou if r["label_iou"] > 0], k)
    if pop.get("objectlab", {}).get("available"):
        scored = [r for r in labels if "objectlab_score" in r]
        scored.sort(key=lambda r: (r["objectlab_score"], r["image"], r["label_index"]))
        m["all_label_objectlab"] = p_at([r["injected_error"] for r in scored], k)
    out["methods"] = {key: round(v, 4) for key, v in m.items()}
    out["aida_legacy_exact"] = m["aida_legacy"]  # 재현 대조는 반올림 전 값으로
    # 누락 층 — 기존 라벨 층과 섞지 않는다
    if rec["condition"].startswith("missing"):
        miss = [v for v in cur["verdicts_by_rank"] if v[1] == "missing"]
        preds = pop["unmatched_predictions"]
        mm = {"n_aida_missing": len(miss), "n_unmatched": len(preds),
              "n_unmatched_matches_dropped": sum(r["matches_dropped"] for r in preds)}
        if miss:
            km = max(1, int(len(miss) * 0.1))
            mm["k_m"] = km
            mm["aida_missing"] = p_at([v[0] for v in miss], km)
            byc = sorted(preds, key=lambda r: (-r["confidence"], r["image"], tuple(r["box"])))
            mm["unmatched_confidence"] = p_at([r["matches_dropped"] for r in byc], km)
            if pop.get("objectlab", {}).get("available"):
                ol = sorted([r for r in preds if "objectlab_overlooked" in r],
                            key=lambda r: (r["objectlab_overlooked"], r["image"], tuple(r["box"])))
                mm["n_unmatched_objectlab_scored"] = len(ol)  # cleanlab 확신도 문턱(0.95) 밖은 NaN
                mm["unmatched_objectlab"] = p_at([r["matches_dropped"] for r in ol], km)
            mm["unmatched_random_expected"] = (mm["n_unmatched_matches_dropped"] / len(preds)
                                               if preds else 0.0)
        out["missing_layer"] = {key: (round(v, 4) if isinstance(v, float) else v)
                                for key, v in mm.items()}
    return out


def _mean(xs):
    return statistics.mean(xs) if xs else None


def _msd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"mean": round(statistics.mean(xs), 4),
            "sd": round(statistics.stdev(xs), 4) if len(xs) > 1 else None, "n_seeds": len(xs)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=HERE / "planning_evidence" / "controlled_baseline_stage2_2026-10-06.json")
    a = ap.parse_args()
    import subprocess
    try:
        import torch, ultralytics, cleanlab  # noqa: E401 — 실행과 같은 venv에서 집계한다
        versions = {"torch": torch.__version__, "ultralytics": ultralytics.__version__,
                    "cleanlab": cleanlab.__version__}
    except ImportError as exc:  # pragma: no cover
        versions = {"error": str(exc)}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
                          text=True).stdout.strip()
    log = (ROOT / "progress.log").read_text(encoding="utf-8").splitlines()
    done = [ln for ln in log if " done " in ln]
    result = {
        "purpose": "controlled baseline stage 2 — re-inference with existing weights, both orderings, "
                   "population (all labels + label_iou + injected truth, unmatched predictions, ObjectLab)",
        "spec": "docs/paper/controlled-baseline-spec.md",
        "synthetic": "injected errors on KITTI/COCO subsets; controlled, not human-adjudicated",
        "git_head_at_analysis": head,
        "code_state": "run + analysis scripts uncommitted at run time (parent commits)",
        "versions": versions,
        "env_rules": {"AIDA_RELIABILITY_PROFILE": "unset", "AIDA_RULER_WEIGHTS": "unset",
                      "group_C_note": "original box_accuracy_eval_mc_ruler_self.json used "
                                      "reliability_profile_mc.json; this rerun does not"},
        "runs": {"condition_runs": len(done), "first": log[0][:19] if log else None,
                 "last": log[-1][:19] if log else None},
        "budget": "k = max(1, floor(0.1 * AIDA findings)) per condition, same k for every method; "
                  "fewer candidates than k -> denominator stays k",
        "units": {"finding": ["aida_legacy", "aida_current", "aida_random_expected",
                              "aida_iou_reorder"],
                  "unique_label": ["aida_current_unique", "all_label_random_expected",
                                   "all_label_iou", "all_label_objectlab",
                                   "all_label_iou_excl0_posthoc"]},
        "aggregation": "existing_label_layer = per-seed mean over non-silent, non-missing_* "
                       "conditions, then mean/sd across seeds; all_conditions_finding_unit includes "
                       "missing_* (comparable with seeded P@10%); missing_layer separate budget",
        "groups": {}}
    for gdir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        g = gdir.name
        meta = json.loads((gdir / "run_meta.json").read_text(encoding="utf-8"))
        conds = meta["conditions"]
        seeded = None
        if g in SEEDED and (HERE / SEEDED[g][0]).exists():
            sd = json.loads((HERE / SEEDED[g][0]).read_text(encoding="utf-8"))
            seeded = (sd, SEEDED[g][1])
        evalref = None
        if g in EVAL_REF and (HERE / EVAL_REF[g]).exists():
            ej = json.loads((HERE / EVAL_REF[g]).read_text(encoding="utf-8"))
            evalref = {r["condition"]: r for r in ej.get("per_condition", [])}
        gout = {"conditions_dir": meta["conditions_dir"], "env": meta["env"],
                "n_conditions": len(conds), "limit": meta["limit"],
                "weights_sha256": meta["weights_sha256"], "rulers": {}}
        for rdir in sorted(p for p in gdir.iterdir() if p.is_dir()):
            ruler = rdir.name
            rout = {"seeds": {}}
            per_seed_existing = {mth: [] for mth in EXISTING_METHODS}
            per_seed_missing = {mth: [] for mth in MISSING_METHODS}
            per_seed_allcond = {"aida_legacy": [], "aida_current": []}
            for sdir in sorted(rdir.iterdir(), key=lambda p: int(p.name[1:])):
                seed = int(sdir.name[1:])
                recs = []
                for c in conds:
                    f = sdir / f"{c}.json.gz"
                    if f.exists():
                        with gzip.open(f, "rt", encoding="utf-8") as fh:
                            recs.append(json.load(fh))
                if len(recs) < len(conds):
                    rout["seeds"][str(seed)] = {"incomplete": f"{len(recs)}/{len(conds)}"}
                    continue
                cm = [condition_metrics(r) for r in recs]
                active = [x for x in cm if not x.get("silent")]
                existing = [x for x in active if not x["condition"].startswith("missing")]
                srow = {"silent": [x["condition"] for x in cm if x.get("silent")],
                        "n_active": len(active), "n_existing_active": len(existing),
                        "per_condition": cm}
                # 재현 확인: legacy P@10% = seeded per_condition (finding 단위, 전 조건)
                if seeded:
                    sd, labels = seeded
                    rows = sd["rulers"].get(labels.get(ruler, ""), [])
                    idx = sd["seeds"].index(seed) if seed in sd["seeds"] else None
                    if idx is not None and idx < len(rows):
                        ref = rows[idx]["per_condition"]
                        mine = {x["condition"]: x["aida_legacy_exact"] for x in active}
                        srow["repro_vs_seeded"] = {
                            "matched": sum(1 for c, v in ref.items()
                                           if c in mine and abs(mine[c] - v) < 1e-12),
                            "n_ref": len(ref), "silent_ref": rows[idx].get("silent", []),
                            "mismatch": [[c, v, mine.get(c)] for c, v in ref.items()
                                         if c not in mine or abs(mine[c] - v) >= 1e-12]}
                if evalref:
                    srow["flagged_tp_vs_eval"] = {
                        "matched": sum(1 for x in cm if x["condition"] in evalref
                                       and evalref[x["condition"]]["flagged"] == x["flagged"]
                                       and evalref[x["condition"]]["tp"] == x["tp"]),
                        "n_ref": sum(1 for x in cm if x["condition"] in evalref)}
                for mth in EXISTING_METHODS:
                    vals = [x["methods"][mth] for x in existing if mth in x["methods"]]
                    srow.setdefault("mean_existing", {})[mth] = (
                        round(_mean(vals), 4) if vals else None)
                    srow.setdefault("n_existing_with_method", {})[mth] = len(vals)
                    per_seed_existing[mth].append(_mean(vals) if vals else None)
                for mth in per_seed_allcond:
                    vals = [x["methods"][mth] for x in active]
                    srow.setdefault("mean_all_conditions", {})[mth] = round(_mean(vals), 4)
                    per_seed_allcond[mth].append(_mean(vals))
                ml = [x["missing_layer"] for x in active if "missing_layer" in x]
                for mth in MISSING_METHODS:
                    vals = [x[mth] for x in ml if mth in x]
                    srow.setdefault("mean_missing_layer", {})[mth] = (
                        round(_mean(vals), 4) if vals else None)
                    per_seed_missing[mth].append(_mean(vals) if vals else None)
                srow["missing_layer_objectlab_scored_total"] = sum(
                    x.get("n_unmatched_objectlab_scored", 0) for x in ml)
                srow["missing_layer_unmatched_total"] = sum(x["n_unmatched"] for x in ml)
                rout["seeds"][str(seed)] = srow
            rout["existing_label_layer"] = {m: _msd(v) for m, v in per_seed_existing.items()}
            rout["all_conditions_finding_unit"] = {m: _msd(v) for m, v in per_seed_allcond.items()}
            rout["missing_layer"] = {m: _msd(v) for m, v in per_seed_missing.items()}
            gout["rulers"][ruler] = rout
        result["groups"][g] = gout
    a.out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    # 짧은 표
    sys.stdout.reconfigure(encoding="utf-8")
    for g, gout in result["groups"].items():
        for ruler, rout in gout["rulers"].items():
            rep = [s.get("repro_vs_seeded") for s in rout["seeds"].values() if "repro_vs_seeded" in s]
            rep_s = (f" repro {sum(r['matched'] for r in rep)}/{sum(r['n_ref'] for r in rep)}"
                     if rep else "")
            ex = rout["existing_label_layer"]
            print(g, ruler, rep_s, {m: (v["mean"] if v else None) for m, v in ex.items()})


if __name__ == "__main__":
    main()
