"""통제 기준선 2단계 집계 — GPU 없음. 입력은 run_controlled_baseline_stage2.py의 조건별 기록.

명세: docs/paper/controlled-baseline-spec.md 3절(2026-10-06 사용자 확정). 조건마다 공통 예산
k = max(1, floor(0.1 × AIDA finding 수))를 한 번 정해 모든 방법에 쓴다. finding 0건 조건은
silent로 모든 방법에서 뺀다. 후보가 k보다 적으면 있는 만큼만 보고 분모는 k(확정) — 그런 조건 수를
방법별로 세고(`denominator_shortfall`), 0보다 크면 실제 후보 수를 분모로 한 변형도 낸다(부록용).

동점(확정): 기준선 정렬의 동점은 고정 씨앗 해시 `sha256(f"{tie_seed}:{candidate_id}")` 오름차순으로
자른다(Q-A D9와 같은 식, `evaluation.coverage.tie_key`). 1차 씨앗 20260929, 민감도 씨앗 1~10.
옛 규칙(이미지 이름 → 라벨 인덱스)의 결과는 `*_tie_name_index` 키로 남긴다(추적용).
후보 id: 라벨·라벨이 있는 finding = "{image}/{label_index}", 미매칭 예측 = "{image}/pred/{box}".
AIDA 제품 순서(legacy·current)는 버전이 정한 순서(안정 정렬, 진단 순)라 다시 자르지 않는다 —
경계 동점(반올림 심각도 기준) 수만 센다.

방법(기존 라벨 층):
  aida_legacy / aida_current   AIDA finding 순서(legacy_severity_v0 / review_order_v1), finding 단위
  aida_random_expected         AIDA finding 안 무작위의 기대값 = TP / flagged, finding 단위
  aida_iou_reorder             AIDA finding을 label_iou 오름차순으로 다시 정렬(동점: 해시, 같은 라벨의
                               finding끼리는 원래 순서), label_iou가 없는 finding(누락 유형)은 뒤에 AIDA
                               순서로. finding 단위
  aida_current_unique          review_order_v1에서 같은 라벨의 두 번째 이후 finding을 건너뛴 고유 단위
  all_label_random_expected    범위 안 전체 라벨의 주입 오류 비율, 고유 라벨 단위
  all_label_iou                전체 라벨 1 − label_iou 내림차순(동점: 해시), 고유 라벨 단위
  all_label_objectlab          전체 라벨 objectlab_score 오름차순(점수 있는 라벨만, 동점: 해시)
  all_label_iou_excl0_posthoc  (사후 보조, 명세 밖) label_iou = 0 라벨을 뺀 all_label_iou
누락 층(missing_* 조건만, 별도 예산 k_m = max(1, floor(0.1 × AIDA 누락 finding 수))):
  aida_missing, unmatched_confidence(확신도 내림차순), unmatched_objectlab(overlooked 오름차순),
  unmatched_random_expected(matches_dropped 비율). 동점은 위와 같은 해시.

사용법: python analyze_controlled_baseline_stage2.py [--out planning_evidence/...json]
"""
import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evaluation.coverage import tie_key  # noqa: E402

ROOT = HERE / "controlled_baseline_stage2"
LEG, CUR = "legacy_severity_v0", "review_order_v1"
PRIMARY_TIE_SEED = 20260929  # Q-A D9와 같은 씨앗
SENSITIVITY_TIE_SEEDS = list(range(1, 11))
NAME_INDEX = None  # 옛 동점 규칙(이미지 이름 → 라벨 인덱스)
EXISTING_METHODS = ["aida_legacy", "aida_current", "aida_random_expected", "aida_iou_reorder",
                    "aida_current_unique", "all_label_random_expected", "all_label_iou",
                    "all_label_objectlab", "all_label_iou_excl0_posthoc"]
MISSING_METHODS = ["aida_missing", "unmatched_confidence", "unmatched_objectlab",
                   "unmatched_random_expected"]
# 해시 동점 규칙이 순위를 바꾸는 방법(나머지는 기대값이거나 제품 순서)
TIE_SENSITIVE = ["aida_iou_reorder", "all_label_iou", "all_label_objectlab",
                 "all_label_iou_excl0_posthoc", "unmatched_confidence", "unmatched_objectlab"]
SEEDED = {"A": ("seeded_ruler4_7seeds.json", {"matched": "자기 도메인", "shifted": "약한 이동",
                                               "far": "먼 이동(1C)", "broad": "넓은 자(800)"}),
          "B": ("seeded_coco_3seeds.json", {"coco_self": "COCO 자기(1C)",
                                            "kitti_on_coco": "KITTI→COCO(1C)"})}
EVAL_REF = {"C": "box_accuracy_eval_mc_ruler_self.json", "D": "box_accuracy_eval.json"}


def p_at(flags: list[bool], k: int) -> float:
    return sum(bool(x) for x in flags[:k]) / k


def p_at_actual(flags: list[bool], k: int) -> float | None:
    """분모를 실제 후보 수 min(k, 후보 수)로 둔 변형(부록용). 후보 0이면 None."""
    n = min(k, len(flags))
    return sum(bool(x) for x in flags[:n]) / n if n else None


def label_id(image: str, label_index) -> str:
    return f"{image}/{label_index}"


def pred_id(r: dict) -> str:
    return f"{r['image']}/pred/{','.join(str(v) for v in r['box'])}"


def _tb(tie_seed, cid: str, fallback: tuple) -> tuple:
    """동점 자르기 키. tie_seed=None이면 옛 규칙(fallback = 이미지 이름, 라벨 인덱스/상자)."""
    return fallback if tie_seed is NAME_INDEX else (tie_key(tie_seed, cid),)


def _ranked(rows: list, value, cid, fallback, tie_seed) -> list:
    return sorted(rows, key=lambda r: (value(r),) + _tb(tie_seed, cid(r), fallback(r)))


def _boundary_tie(values: list, k: int) -> bool:
    """k번째와 k+1번째의 정렬 값이 같으면 동점 규칙이 상위 k의 구성을 정한다."""
    return len(values) > k and values[k - 1] == values[k]


def condition_metrics(rec: dict, tie_seed=PRIMARY_TIE_SEED) -> dict:
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
    m, ncand, btie, actual = {}, {}, {}, {}

    def put(name, flags, values=None):
        m[name] = p_at(flags, k)
        ncand[name] = len(flags)
        actual[name] = p_at_actual(flags, k)
        if values is not None:
            btie[name] = _boundary_tie(values, k)

    lv = [v for v in leg["verdicts_by_rank"]]
    put("aida_legacy", [v[0] for v in lv], [v[2] for v in lv])
    present = set(cur.get("present_types") or [])
    cv = cur["verdicts_by_rank"]
    put("aida_current", [v[0] for v in cv], [(v[1] not in present, v[2]) for v in cv])
    m["aida_random_expected"] = cur["tp"] / flagged
    iou = {(r["image"], r["label_index"]): r["label_iou"] for r in labels}
    items = [(v[0], tuple(fid), i) for i, (v, fid) in
             enumerate(zip(cv, cur["finding_ids_by_rank"]))]
    with_iou = [x for x in items if x[1] in iou]
    without = [x for x in items if x[1] not in iou]
    with_iou.sort(key=lambda x: (iou[x[1]],) + _tb(tie_seed, label_id(*x[1]), x[1]) + (x[2],))
    out["aida_findings_with_label_iou"] = len(with_iou)
    put("aida_iou_reorder", [x[0] for x in with_iou + without],
        [iou[x[1]] for x in with_iou] + [("aida_order", x[2]) for x in without])
    seen, uniq = set(), []
    for c, fid, _ in items:
        if fid[1] is not None:
            if fid in seen:
                continue
            seen.add(fid)
        uniq.append(c)
    put("aida_current_unique", uniq)
    m["all_label_random_expected"] = (out["n_injected_labels"] / len(labels)) if labels else 0.0
    lid = lambda r: label_id(r["image"], r["label_index"])  # noqa: E731
    lfb = lambda r: (r["image"], r["label_index"])  # noqa: E731
    by_iou = _ranked(labels, lambda r: r["label_iou"], lid, lfb, tie_seed)
    put("all_label_iou", [r["injected_error"] for r in by_iou], [r["label_iou"] for r in by_iou])
    # 사후 보조(명세 밖): label_iou = 0(짝 예측 없음) 라벨이 상위 k를 채우는지 보려고 뺀 변형
    out["n_labels_iou0"] = sum(1 for r in labels if r["label_iou"] == 0)
    nz = [r for r in by_iou if r["label_iou"] > 0]
    put("all_label_iou_excl0_posthoc", [r["injected_error"] for r in nz],
        [r["label_iou"] for r in nz])
    if pop.get("objectlab", {}).get("available"):
        scored = _ranked([r for r in labels if "objectlab_score" in r],
                         lambda r: r["objectlab_score"], lid, lfb, tie_seed)
        put("all_label_objectlab", [r["injected_error"] for r in scored],
            [r["objectlab_score"] for r in scored])
    out["methods"] = {key: round(v, 4) for key, v in m.items()}
    out["n_candidates"] = ncand
    out["denominator_shortfall"] = sorted(n for n, c in ncand.items() if c < k)
    out["methods_actual_denominator"] = {
        n: (round(actual[n], 4) if actual[n] is not None else None)
        for n in out["denominator_shortfall"]}
    out["boundary_tie"] = sorted(n for n, t in btie.items() if t)
    out["aida_legacy_exact"] = m["aida_legacy"]  # 재현 대조는 반올림 전 값으로
    # 누락 층 — 기존 라벨 층과 섞지 않는다
    if rec["condition"].startswith("missing"):
        miss = [v for v in cv if v[1] == "missing"]
        preds = pop["unmatched_predictions"]
        mm = {"n_aida_missing": len(miss), "n_unmatched": len(preds),
              "n_unmatched_matches_dropped": sum(r["matches_dropped"] for r in preds)}
        mshort, mact, mtie = [], {}, []
        if miss:
            km = max(1, int(len(miss) * 0.1))
            mm["k_m"] = km

            def mput(name, flags, values=None):
                mm[name] = p_at(flags, km)
                if len(flags) < km:
                    mshort.append(name)
                    mact[name] = p_at_actual(flags, km)
                if values is not None and _boundary_tie(values, km):
                    mtie.append(name)

            mput("aida_missing", [v[0] for v in miss], [v[2] for v in miss])
            pfb = lambda r: (r["image"], tuple(r["box"]))  # noqa: E731
            byc = _ranked(preds, lambda r: -r["confidence"], pred_id, pfb, tie_seed)
            mput("unmatched_confidence", [r["matches_dropped"] for r in byc],
                 [r["confidence"] for r in byc])
            if pop.get("objectlab", {}).get("available"):
                ol = _ranked([r for r in preds if "objectlab_overlooked" in r],
                             lambda r: r["objectlab_overlooked"], pred_id, pfb, tie_seed)
                mm["n_unmatched_objectlab_scored"] = len(ol)  # cleanlab 확신도 문턱(0.95) 밖은 NaN
                mput("unmatched_objectlab", [r["matches_dropped"] for r in ol],
                     [r["objectlab_overlooked"] for r in ol])
            mm["unmatched_random_expected"] = (mm["n_unmatched_matches_dropped"] / len(preds)
                                               if preds else 0.0)
        out["missing_layer"] = {key: (round(v, 4) if isinstance(v, float) else v)
                                for key, v in mm.items()}
        out["missing_layer"]["denominator_shortfall"] = sorted(mshort)
        out["missing_layer"]["methods_actual_denominator"] = {
            n: (round(v, 4) if v is not None else None) for n, v in mact.items()}
        out["missing_layer"]["boundary_tie"] = sorted(mtie)
    return out


def _mean(xs):
    return statistics.mean(xs) if xs else None


def _msd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"mean": round(statistics.mean(xs), 4),
            "sd": round(statistics.stdev(xs), 4) if len(xs) > 1 else None, "n_seeds": len(xs)}


def layer_means(cm: list[dict]) -> dict:
    """한 시드의 조건별 지표 → 층별 조건 평균(기존 라벨 층은 missing_* 제외)."""
    active = [x for x in cm if not x.get("silent")]
    existing = [x for x in active if not x["condition"].startswith("missing")]
    ex = {}
    for mth in EXISTING_METHODS:
        vals = [x["methods"][mth] for x in existing if mth in x["methods"]]
        ex[mth] = _mean(vals) if vals else None
    ml = [x["missing_layer"] for x in active if "missing_layer" in x]
    mi = {}
    for mth in MISSING_METHODS:
        vals = [x[mth] for x in ml if mth in x]
        mi[mth] = _mean(vals) if vals else None
    return {"existing": ex, "missing": mi}


def shortfall_summary(cm: list[dict]) -> dict:
    """한 시드: 방법별로 후보가 k보다 적었던 조건 수와 실제 분모 변형의 조건 평균(후보 0건 조건은 평균에서 뺌)."""
    active = [x for x in cm if not x.get("silent")]
    existing = [x for x in active if not x["condition"].startswith("missing")]
    ml = [x["missing_layer"] for x in active if "missing_layer" in x and "k_m" in x["missing_layer"]]
    res = {"existing_label_layer": {}, "missing_layer": {}}
    for mth in EXISTING_METHODS:
        have = [x for x in existing if mth in x.get("n_candidates", {})]
        short = [x for x in have if mth in x["denominator_shortfall"]]
        acts = [x["methods_actual_denominator"].get(mth, x["methods"][mth])
                if mth in x["denominator_shortfall"] else x["methods"][mth] for x in have]
        res["existing_label_layer"][mth] = {
            "n_conditions": len(have), "n_short": len(short),
            "n_zero_candidates": sum(1 for x in short if x["n_candidates"][mth] == 0),
            "mean_actual_denominator": _mean([a for a in acts if a is not None])}
    for mth in MISSING_METHODS:
        if mth == "unmatched_random_expected":
            continue
        have = [x for x in ml if mth in x]
        short = [x for x in have if mth in x["denominator_shortfall"]]
        acts = [x["methods_actual_denominator"][mth] if mth in x["denominator_shortfall"]
                else x[mth] for x in have]
        res["missing_layer"][mth] = {
            "n_conditions": len(have), "n_short": len(short),
            "n_zero_candidates": sum(1 for x in short
                                     if x["methods_actual_denominator"][mth] is None),
            "mean_actual_denominator": _mean([a for a in acts if a is not None])}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "planning_evidence"
                    / "controlled_baseline_stage2_tieseed_2026-10-06.json")
    a = ap.parse_args()
    import subprocess
    try:
        import cleanlab  # noqa: F401 — 집계는 cleanlab 점수를 다시 내지 않는다(기록된 값만 읽음)
        versions = {"cleanlab": cleanlab.__version__}
    except ImportError as exc:  # pragma: no cover
        versions = {"error": str(exc)}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
                          text=True).stdout.strip()
    log = (ROOT / "progress.log").read_text(encoding="utf-8").splitlines()
    done = [ln for ln in log if " done " in ln]
    variants = [PRIMARY_TIE_SEED, NAME_INDEX] + SENSITIVITY_TIE_SEEDS
    result = {
        "purpose": "controlled baseline stage 2 — re-aggregation of the same raw records with the "
                   "user-confirmed (2026-10-06) tie rule (seeded sha256 hash), tie-seed sensitivity, "
                   "and denominator-shortfall counts. No re-inference.",
        "spec": "docs/paper/controlled-baseline-spec.md",
        "previous_evidence": "experiment/planning_evidence/controlled_baseline_stage2_2026-10-06.json "
                             "(old tie rule; kept unchanged)",
        "synthetic": "injected errors on KITTI/COCO subsets; controlled, not human-adjudicated",
        "git_head_at_analysis": head,
        "versions_at_analysis": versions,
        "env_rules": {"AIDA_RELIABILITY_PROFILE": "unset", "AIDA_RULER_WEIGHTS": "unset",
                      "group_C_note": "original box_accuracy_eval_mc_ruler_self.json used "
                                      "reliability_profile_mc.json; this rerun does not"},
        "runs": {"condition_runs": len(done), "first": log[0][:19] if log else None,
                 "last": log[-1][:19] if log else None},
        "budget": "k = max(1, floor(0.1 * AIDA findings)) per condition, same k for every method; "
                  "fewer candidates than k -> denominator stays k (user-confirmed 2026-10-06). "
                  "denominator_shortfall counts conditions where that happened; "
                  "mean_actual_denominator uses min(k, candidates) (appendix variant, conditions "
                  "with 0 candidates excluded)",
        "tie_rule": {"rule": "ascending sha256(f'{tie_seed}:{candidate_id}') after the method's "
                             "sort value (same formula as Q-A D9, evaluation.coverage.tie_key)",
                     "primary_tie_seed": PRIMARY_TIE_SEED,
                     "sensitivity_tie_seeds": SENSITIVITY_TIE_SEEDS,
                     "candidate_id": {"label_or_label_finding": "{image}/{label_index}",
                                      "unmatched_prediction": "{image}/pred/{x1,y1,x2,y2 as stored}"},
                     "applies_to": TIE_SENSITIVE,
                     "not_applied": "aida_legacy / aida_current / aida_missing keep the versioned "
                                    "product order (stable sort, diagnosis order); random baselines "
                                    "are expected values",
                     "old_rule_key_suffix": "_tie_name_index (image name, label index / box)",
                     "user_confirmed": "2026-10-06"},
        "boundary_tie_note": "n_boundary_tie counts conditions where the k-th and (k+1)-th sort "
                             "values are equal; AIDA product orders use 4-decimal rounded severity "
                             "(and systemic membership for review_order_v1), so their count is an "
                             "upper bound and no tie rule is applied to them",
        "units": {"finding": ["aida_legacy", "aida_current", "aida_random_expected",
                              "aida_iou_reorder"],
                  "unique_label": ["aida_current_unique", "all_label_random_expected",
                                   "all_label_iou", "all_label_objectlab",
                                   "all_label_iou_excl0_posthoc"]},
        "aggregation": "existing_label_layer = per-seed mean over non-silent, non-missing_* "
                       "conditions, then mean/sd across seeds; all_conditions_finding_unit = AIDA "
                       "orders over all non-silent conditions incl. missing_* (same set as seeded "
                       "top10; tie rule irrelevant); missing_layer separate budget; "
                       "tie_seed_sensitivity = min/max over the 10 sensitivity tie seeds of the "
                       "across-seed mean",
        "groups": {}}
    for gdir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        g = gdir.name
        meta = json.loads((gdir / "run_meta.json").read_text(encoding="utf-8"))
        conds = meta["conditions"]
        seeded = None
        if g in SEEDED and (HERE / SEEDED[g][0]).exists():
            sd = json.loads((HERE / SEEDED[g][0]).read_text(encoding="utf-8"))
            seeded = (sd, SEEDED[g][1])
        gout = {"conditions_dir": meta["conditions_dir"], "n_conditions": len(conds),
                "limit": meta["limit"], "rulers": {}}
        for rdir in sorted(p for p in gdir.iterdir() if p.is_dir()):
            ruler = rdir.name
            rout = {"seeds": {}}
            per_var = {str(v): {"existing": {m: [] for m in EXISTING_METHODS},
                                "missing": {m: [] for m in MISSING_METHODS}} for v in variants}
            short_acc, tie_acc, allcond = {}, {}, {}
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
                cms = {str(v): [condition_metrics(r, v) for r in recs] for v in variants}
                cm = cms[str(PRIMARY_TIE_SEED)]
                srow = {"silent": [x["condition"] for x in cm if x.get("silent")]}
                if seeded:
                    sd, lab = seeded
                    rows = sd["rulers"].get(lab.get(ruler, ""), [])
                    idx = sd["seeds"].index(seed) if seed in sd["seeds"] else None
                    if idx is not None and idx < len(rows):
                        ref = rows[idx]["per_condition"]
                        mine = {x["condition"]: x["aida_legacy_exact"] for x in cm
                                if not x.get("silent")}
                        srow["repro_vs_seeded"] = {
                            "matched": sum(1 for c, v in ref.items()
                                           if c in mine and abs(mine[c] - v) < 1e-12),
                            "n_ref": len(ref)}
                for v, vcm in cms.items():
                    lm = layer_means(vcm)
                    for layer in ("existing", "missing"):
                        for mth, val in lm[layer].items():
                            per_var[v][layer][mth].append(val)
                lm = layer_means(cm)
                srow["mean_existing"] = {m: (round(x, 4) if x is not None else None)
                                         for m, x in lm["existing"].items()}
                srow["mean_missing_layer"] = {m: (round(x, 4) if x is not None else None)
                                              for m, x in lm["missing"].items()}
                active_cm = [x for x in cm if not x.get("silent")]
                srow["mean_all_conditions"] = {}
                for mth in ("aida_legacy", "aida_current"):  # seeded top10과 같은 정의(전 조건)
                    val = _mean([x["methods"][mth] for x in active_cm])
                    srow["mean_all_conditions"][mth] = round(val, 4)
                    allcond.setdefault(mth, []).append(val)
                srow["per_condition"] = [
                    {key: x[key] for key in ("condition", "k", "methods", "n_candidates",
                                             "denominator_shortfall", "boundary_tie",
                                             "missing_layer") if key in x} for x in cm]
                rout["seeds"][str(seed)] = srow
                # 부족분·경계 동점 누적(동점 규칙과 무관 — 1차 씨앗 기준)
                ss = shortfall_summary(cm)
                for layer, d in ss.items():
                    for mth, s in d.items():
                        acc = short_acc.setdefault(layer, {}).setdefault(
                            mth, {"n_condition_runs": 0, "n_short": 0, "n_zero_candidates": 0,
                                  "per_seed_mean_actual_denominator": []})
                        acc["n_condition_runs"] += s["n_conditions"]
                        acc["n_short"] += s["n_short"]
                        acc["n_zero_candidates"] += s["n_zero_candidates"]
                        acc["per_seed_mean_actual_denominator"].append(
                            s["mean_actual_denominator"])
                active = [x for x in cm if not x.get("silent")]
                for x in active:
                    if not x["condition"].startswith("missing"):
                        for mth in x["boundary_tie"]:
                            tie_acc.setdefault("existing_label_layer", {}).setdefault(mth, 0)
                            tie_acc["existing_label_layer"][mth] += 1
                    for mth in x.get("missing_layer", {}).get("boundary_tie", []):
                        tie_acc.setdefault("missing_layer", {}).setdefault(mth, 0)
                        tie_acc["missing_layer"][mth] += 1
            P, O = str(PRIMARY_TIE_SEED), str(NAME_INDEX)
            rout["all_conditions_finding_unit"] = {m: _msd(v) for m, v in allcond.items()}
            rout["existing_label_layer"] = {m: _msd(v) for m, v in per_var[P]["existing"].items()}
            rout["missing_layer"] = {m: _msd(v) for m, v in per_var[P]["missing"].items()}
            rout["existing_label_layer_tie_name_index"] = {
                m: _msd(v) for m, v in per_var[O]["existing"].items()}
            rout["missing_layer_tie_name_index"] = {
                m: _msd(v) for m, v in per_var[O]["missing"].items()}
            sens = {"existing_label_layer": {}, "missing_layer": {}}
            for layer, key in (("existing", "existing_label_layer"), ("missing", "missing_layer")):
                methods = EXISTING_METHODS if layer == "existing" else MISSING_METHODS
                for mth in methods:
                    if mth not in TIE_SENSITIVE:
                        continue
                    means = [(_msd(per_var[str(t)][layer][mth]) or {}).get("mean")
                             for t in SENSITIVITY_TIE_SEEDS]
                    means = [x for x in means if x is not None]
                    if means:
                        sens[key][mth] = {"min": min(means), "max": max(means),
                                          "n_tie_seeds": len(means)}
            rout["tie_seed_sensitivity"] = sens
            for layer, d in short_acc.items():
                for mth, acc in d.items():
                    vals = acc.pop("per_seed_mean_actual_denominator")
                    acc["mean_actual_denominator"] = (_msd(vals) if acc["n_short"] else None)
            rout["denominator_shortfall"] = short_acc
            rout["n_boundary_tie"] = tie_acc
            gout["rulers"][ruler] = rout
        result["groups"][g] = gout
    a.out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for g, gout in result["groups"].items():
        for ruler, rout in gout["rulers"].items():
            ex = rout["existing_label_layer"]
            print(g, ruler, {m: (v["mean"] if v else None) for m, v in ex.items()})
            print("   sens", rout["tie_seed_sensitivity"])
            print("   short", {L: {m: (s["n_short"], s["n_condition_runs"]) for m, s in d.items()
                                   if s["n_short"]} for L, d in rout["denominator_shortfall"].items()})
            print("   ties", rout["n_boundary_tie"])


if __name__ == "__main__":
    main()
