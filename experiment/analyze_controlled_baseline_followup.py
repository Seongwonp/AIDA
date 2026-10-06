"""통제 기준선 후속 분석 — 저장된 원시 기록의 재집계만(재추론·학습·GPU 없음).

설계: docs/paper/controlled-baseline-followup-plan.md (2026-10-06 확정).
입력: experiment/controlled_baseline_stage2/ (git 무시, 조건별 *.json.gz + summary.json + run_meta.json),
      experiment/planning_evidence/controlled_baseline_stage2_tieseed_2026-10-06.json (표 6의 근거).

순서:
  0. 원시 기록 완전성 — 존재·읽기·필수 필드·목록 길이·summary 대응·finding ID↔라벨 ID. 결과를 먼저 파일로 쓴다.
     같은 k(동점 씨앗 20260929)에서 표 6(tieseed 파일의 조건별 값·층 평균)이 재현되지 않으면 거기서 멈춘다.
  A. 짝지은 차이 AIDA current − 기준선(전체 라벨 ObjectLab·1−IoU·무작위 기대값), 기존 라벨 층(missing_* 제외).
     조건·시드별 차이 → 시드별 조건 평균 → 시드 간 평균. 조건은 재표집하지 않는다. 시드별 평균의 탐색적 t 구간
     (자유도 = 시드 수 − 1, 단일 시드 묶음은 구간 없음). 동점 씨앗 1~10은 별도 민감도(합치지 않음).
  B. k 민감도 두 계열: AIDA 지목 수 기준 5·10·20·50%, 전체 라벨 수 기준 1·2·5% (k = max(1, ⌊p × n⌋)).
     분모 k, 후보 부족 수와 실제 분모 변형 병기, 무작위 기대값은 × min(k, 후보 수)/k. finding 단위와 고유 라벨 단위
     표를 나눈다. 조건별 IoU 0 라벨 수와 k > IoU 0 수 여부를 기록한다(IoU 0 라벨은 빼지 않는다).
  C. +0.41 대체 자료: 저장된 자별 legacy → current의 @k(P@10%)와 @5(상위 5건). 두 지표는 다른 값이다.

사용법: python analyze_controlled_baseline_followup.py [--date 2026-10-06]
기존 출력 파일이 있으면 덮어쓰지 않고 멈춘다.
"""
import argparse
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_controlled_baseline_stage2 as A2  # noqa: E402

ROOT = A2.ROOT
LEG, CUR = A2.LEG, A2.CUR
PRIMARY = A2.PRIMARY_TIE_SEED
SENS = A2.SENSITIVITY_TIE_SEEDS
TIESEED_JSON = HERE / "planning_evidence" / "controlled_baseline_stage2_tieseed_2026-10-06.json"

# 기대 구성(명세 6절): 묶음 → (자 목록, 시드 목록). 조건 목록은 run_meta.json에서 읽는다.
EXPECTED = {
    "A": (["matched", "shifted", "far", "broad"], [7, 42, 123, 777, 2024, 2025, 31337]),
    "B": (["coco_self", "kitti_on_coco"], [42, 123, 2024]),
    "C": (["self"], [42]),
    "D": (["kitti_car_clean"], [42]),
}
EXPECTED_N_CONDITIONS = {"A": 29, "B": 26, "C": 29, "D": 26}

FINDING_PCTS = [5, 10, 20, 50]   # AIDA 지목 수의 %
LABEL_PCTS = [1, 2, 5]           # 전체 라벨 수의 %
K_KEYS = [f"f{p}" for p in FINDING_PCTS] + [f"l{p}" for p in LABEL_PCTS]

FINDING_UNIT = ["aida_legacy", "aida_current", "aida_random_expected", "aida_iou_reorder"]
UNIQUE_UNIT = ["aida_current_unique", "all_label_random_expected", "all_label_iou",
               "all_label_objectlab"]
TIE_SENSITIVE = ["aida_iou_reorder", "all_label_iou", "all_label_objectlab"]
BASELINES = ["all_label_objectlab", "all_label_iou", "all_label_random_expected"]


# ---------------------------------------------------------------- 공통 계산
def k_of(n: int, pct: int) -> int:
    """k = max(1, ⌊pct/100 × n⌋), 정수 산술(부동소수 경계 오차 없음)."""
    return max(1, (n * pct) // 100)


def precision_top(flags: list, k: int) -> float:
    """`evaluate_box_accuracy.precision_at_k`와 같은 정의(분모 = min(k, 후보 수)) — @5용."""
    top = flags[:k]
    return sum(bool(x) for x in top) / len(top) if top else 0.0


# t 분포 0.975 분위수(scipy.stats.t.ppf와 소수 9자리까지 같음). CI에는 scipy가 없어 표로 둔다.
_T975 = {1: 12.706204736, 2: 4.302652730, 3: 3.182446305, 4: 2.776445105, 5: 2.570581836,
         6: 2.446911851, 7: 2.364624252, 8: 2.306004135, 9: 2.262157163, 10: 2.228138852}


def t_quantile(df: int) -> float:
    if df in _T975:
        return _T975[df]
    from scipy.stats import t   # 표 밖은 scipy가 있을 때만
    return float(t.ppf(0.975, df))


def paired_summary(diffs: dict) -> dict:
    """diffs[seed][condition] = 같은 조건·시드의 차이. 시드별 조건 평균 → 시드 간 평균.

    조건은 고정(재표집 없음). 구간은 시드별 평균의 탐색적 t 구간(자유도 = 시드 수 − 1), 시드 1개면 없음.
    """
    seeds = sorted(diffs)
    seed_means = [statistics.mean(diffs[s].values()) for s in seeds]
    conds = sorted(set().union(*[set(diffs[s]) for s in seeds])) if seeds else []
    cond_means = {c: statistics.mean([diffs[s][c] for s in seeds if c in diffs[s]]) for c in conds}
    n = len(seed_means)
    out = {"n_seeds": n, "n_conditions": len(conds),
           "mean": round(statistics.mean(seed_means), 4) if n else None,
           "sd_across_seeds": round(statistics.stdev(seed_means), 4) if n > 1 else None,
           "per_seed_mean": {str(s): round(m, 4) for s, m in zip(seeds, seed_means)},
           "seeds_positive": f"{sum(m > 0 for m in seed_means)}/{n}",
           "conditions_positive": f"{sum(v > 0 for v in cond_means.values())}/{len(conds)}",
           "conditions_zero": sum(v == 0 for v in cond_means.values()),
           "conditions_negative": sum(v < 0 for v in cond_means.values()),
           "exploratory_t95": None}
    if n > 1:
        half = t_quantile(n - 1) * statistics.stdev(seed_means) / math.sqrt(n)
        m = statistics.mean(seed_means)
        out["exploratory_t95"] = [round(m - half, 4), round(m + half, 4)]
        out["t_df"] = n - 1
    return out


def ranked_lists(rec: dict, tie_seed) -> dict:
    """한 조건 기록 → 방법별 순서대로 늘어선 정답 여부 목록(k와 무관하게 한 번만 정렬).

    정렬은 `analyze_controlled_baseline_stage2.condition_metrics`와 같은 규칙이다(테스트가 k=10%에서 대조).
    """
    cur, leg = rec["rows"][CUR], rec["rows"][LEG]
    labels = rec["population"]["all_labels"]
    cv = cur["verdicts_by_rank"]
    out = {"aida_legacy": [v[0] for v in leg["verdicts_by_rank"]],
           "aida_current": [v[0] for v in cv]}
    iou = {(r["image"], r["label_index"]): r["label_iou"] for r in labels}
    items = [(v[0], tuple(fid), i) for i, (v, fid) in enumerate(zip(cv, cur["finding_ids_by_rank"]))]
    with_iou = [x for x in items if x[1] in iou]
    without = [x for x in items if x[1] not in iou]
    with_iou.sort(key=lambda x: (iou[x[1]],) + A2._tb(tie_seed, A2.label_id(*x[1]), x[1]) + (x[2],))
    out["aida_iou_reorder"] = [x[0] for x in with_iou + without]
    seen, uniq = set(), []
    for c, fid, _ in items:
        if fid[1] is not None:
            if fid in seen:
                continue
            seen.add(fid)
        uniq.append(c)
    out["aida_current_unique"] = uniq
    lid = lambda r: A2.label_id(r["image"], r["label_index"])  # noqa: E731
    lfb = lambda r: (r["image"], r["label_index"])  # noqa: E731
    out["all_label_iou"] = [r["injected_error"] for r in
                            A2._ranked(labels, lambda r: r["label_iou"], lid, lfb, tie_seed)]
    if rec["population"].get("objectlab", {}).get("available"):
        out["all_label_objectlab"] = [r["injected_error"] for r in A2._ranked(
            [r for r in labels if "objectlab_score" in r], lambda r: r["objectlab_score"],
            lid, lfb, tie_seed)]
    return out


def metrics_at(lists: dict, k: int, rec_info: dict, methods=None) -> dict:
    """상위 k 정밀도(분모 k), 후보 수, 실제 분모 변형. 무작위 기대값은 × min(k, 후보 수)/k."""
    res = {}
    for name, flags in lists.items():
        if methods is not None and name not in methods:
            continue
        res[name] = {"v": A2.p_at(flags, k), "n": len(flags), "act": A2.p_at_actual(flags, k)}
    if methods is None or "aida_random_expected" in methods:
        fl, tp = rec_info["flagged"], rec_info["tp"]
        base = tp / fl if fl else 0.0
        res["aida_random_expected"] = {"v": base * min(k, fl) / k, "n": fl,
                                       "act": base if fl else None}
    if methods is None or "all_label_random_expected" in methods:
        nl, ni = rec_info["n_labels"], rec_info["n_injected"]
        base = ni / nl if nl else 0.0
        res["all_label_random_expected"] = {"v": base * min(k, nl) / k, "n": nl,
                                            "act": base if nl else None}
    return res


# ---------------------------------------------------------------- 0. 완전성
def check_record(rec: dict, cond: str, summary: dict | None) -> dict:
    """필수 필드·목록 길이·summary 대응·finding ID↔라벨 ID. missing_fields가 비어 있지 않으면 제외 대상."""
    missing, length, out = [], [], {}
    rows = rec.get("rows") or {}
    for o in (LEG, CUR):
        r = rows.get(o)
        if not isinstance(r, dict):
            missing.append(f"rows.{o}")
            continue
        for f in ("verdicts_by_rank", "finding_ids_by_rank", "tp", "flagged"):
            if f not in r:
                missing.append(f"rows.{o}.{f}")
    if isinstance(rows.get(CUR), dict) and "present_types" not in rows[CUR]:
        missing.append(f"rows.{CUR}.present_types")
    pop = rec.get("population") or {}
    labels = pop.get("all_labels")
    if not isinstance(labels, list):
        missing.append("population.all_labels")
        labels = []
    if not isinstance(pop.get("unmatched_predictions"), list):
        missing.append("population.unmatched_predictions")
    ol = pop.get("objectlab")
    if not isinstance(ol, dict) or not ol.get("available"):
        missing.append("population.objectlab.available")
    bad_label = sum(1 for r in labels if not all(f in r for f in
                                                ("image", "label_index", "label_iou", "injected_error")))
    if bad_label:
        missing.append(f"population.all_labels[*] fields ({bad_label} labels)")
    preds = pop.get("unmatched_predictions") or []
    bad_pred = sum(1 for r in preds if not all(f in r for f in
                                              ("image", "box", "confidence", "matches_dropped")))
    if bad_pred:
        missing.append(f"population.unmatched_predictions[*] fields ({bad_pred} predictions)")
    n_ol = sum(1 for r in labels if "objectlab_score" in r)
    out["labels_without_objectlab_score"] = len(labels) - n_ol
    if isinstance(ol, dict) and ol.get("labels_scored") is not None and ol["labels_scored"] != n_ol:
        length.append(f"objectlab.labels_scored {ol['labels_scored']} != scored labels {n_ol}")
    if missing:
        out["missing_fields"] = missing
        return out
    label_ids = {(r["image"], r["label_index"]) for r in labels}
    if len(label_ids) != len(labels):
        length.append(f"duplicate label ids {len(labels) - len(label_ids)}")
    fids = {}
    for o in (LEG, CUR):
        r = rows[o]
        v, f = r["verdicts_by_rank"], r["finding_ids_by_rank"]
        if not (len(v) == len(f) == r["flagged"]):
            length.append(f"{o}: verdicts {len(v)} / finding_ids {len(f)} / flagged {r['flagged']}")
        if sum(bool(x[0]) for x in v) != r["tp"]:
            length.append(f"{o}: sum(verdict) != tp {r['tp']}")
        fids[o] = sorted((str(a), -1 if b is None else b) for a, b in f)
        if summary is not None and v:
            ref = summary.get(o, {}).get("per_condition", {}).get(cond)
            mine = A2.p_at([x[0] for x in v], max(1, int(len(v) * 0.1)))
            if ref is None or abs(ref - mine) > 1e-12:
                length.append(f"{o}: summary per_condition {ref} != recomputed {mine}")
        if summary is not None and not v and cond not in summary.get(o, {}).get("silent", []):
            length.append(f"{o}: silent but not in summary.silent")
    if fids[LEG] != fids[CUR]:
        length.append("legacy and current finding id multisets differ")
    cur = rows[CUR]
    breaks = type_mismatch = 0
    for v, (img, li) in zip(cur["verdicts_by_rank"], cur["finding_ids_by_rank"]):
        if li is not None and (img, li) not in label_ids:
            breaks += 1
        if (v[1] == "missing") != (li is None):
            type_mismatch += 1
    out["finding_label_id_breaks"] = breaks
    out["finding_type_vs_label_index_mismatch"] = type_mismatch
    out["n_findings"] = cur["flagged"]
    out["n_labels"] = len(labels)
    out["n_unmatched_predictions"] = len(preds)
    if length:
        out["length_or_summary_mismatch"] = length
    return out


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 레코드 하나 → 압축 결과
def compact_record(rec: dict) -> dict:
    """원시 기록 하나에서 A·B·C와 재현 대조에 필요한 값만 남긴다(메모리 절약)."""
    cur = rec["rows"][CUR]
    labels = rec["population"]["all_labels"]
    info = {"flagged": len(cur["verdicts_by_rank"]), "tp": cur["tp"], "n_labels": len(labels),
            "n_injected": sum(r["injected_error"] for r in labels),
            "n_iou0": sum(1 for r in labels if r["label_iou"] == 0)}
    out = {"condition": rec["condition"], "info": info}
    # 재현 대조: 기존 집계 함수(독립 경로)로 1차 씨앗 값
    cm = A2.condition_metrics(rec, PRIMARY)
    out["stage2_primary"] = {k: cm[k] for k in ("k", "methods") if k in cm}
    if info["flagged"] == 0:
        out["silent"] = True
        return out
    ks = {f"f{p}": k_of(info["flagged"], p) for p in FINDING_PCTS}
    ks.update({f"l{p}": k_of(info["n_labels"], p) for p in LABEL_PCTS})
    out["ks"] = ks
    by_tie = {}
    for t in [PRIMARY] + SENS:
        lists = ranked_lists(rec, t)
        methods = None if t == PRIMARY else TIE_SENSITIVE
        by_tie[str(t)] = {kk: metrics_at(lists, kv, info, methods) for kk, kv in ks.items()}
        if t == PRIMARY:
            out["at5"] = {m: precision_top(lists[m], 5) for m in ("aida_legacy", "aida_current")}
            out["current_unique_equals_current_f10"] = (
                A2.p_at(lists["aida_current_unique"], ks["f10"]) == A2.p_at(lists["aida_current"], ks["f10"]))
    out["by_tie"] = by_tie
    return out


# ---------------------------------------------------------------- 집계
def is_existing(cond: str) -> bool:
    return not cond.startswith("missing")


def msd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"mean": round(statistics.mean(xs), 4),
            "sd": round(statistics.stdev(xs), 4) if len(xs) > 1 else None, "n_seeds": len(xs)}


def section_a(store: dict) -> dict:
    """store[seed][cond] = compact record. 기존 라벨 층, k = f10."""
    res = {}
    for base in BASELINES:
        def diffs_for(t, metric_cur="aida_current"):
            d = {}
            for s, recs in store.items():
                for c, r in recs.items():
                    if r.get("silent") or not is_existing(c):
                        continue
                    pr = r["by_tie"][str(PRIMARY)]["f10"]
                    tb = r["by_tie"][str(t)]["f10"]
                    bv = (tb if base in TIE_SENSITIVE else pr).get(base)
                    if bv is None or metric_cur not in pr:
                        continue
                    d.setdefault(s, {})[c] = pr[metric_cur]["v"] - bv["v"]
            return d
        entry = {"primary_tie_seed": paired_summary(diffs_for(PRIMARY))}
        if base in TIE_SENSITIVE:
            sens = {str(t): paired_summary(diffs_for(t)) for t in SENS}
            means = [v["mean"] for v in sens.values()]
            entry["tie_seed_sensitivity"] = {
                "mean_min": min(means), "mean_max": max(means),
                "seeds_positive_by_tie_seed": {t: v["seeds_positive"] for t, v in sens.items()},
                "conditions_positive_by_tie_seed": {t: v["conditions_positive"] for t, v in sens.items()},
                "mean_by_tie_seed": {t: v["mean"] for t, v in sens.items()}}
        entry["unique_label_unit_check"] = paired_summary(diffs_for(PRIMARY, "aida_current_unique"))["mean"]
        res[f"aida_current_minus_{base}"] = entry
    return res


def section_b(store: dict) -> dict:
    res = {"finding_unit": {}, "unique_label_unit": {}, "paired_unique_current_minus_baseline": {},
           "iou0": {}}
    n_runs = 0
    for kk in K_KEYS:
        for unit, methods in (("finding_unit", FINDING_UNIT), ("unique_label_unit", UNIQUE_UNIT)):
            tab = {}
            for m in methods:
                per_seed, per_seed_act, short, zero, runs = [], [], 0, 0, 0
                sens_means = {str(t): [] for t in SENS} if m in TIE_SENSITIVE else None
                for s, recs in store.items():
                    vals, acts = [], []
                    svals = {str(t): [] for t in SENS} if sens_means is not None else None
                    for c, r in recs.items():
                        if r.get("silent") or not is_existing(c):
                            continue
                        x = r["by_tie"][str(PRIMARY)][kk].get(m)
                        if x is None:
                            continue
                        runs += 1
                        k = r["ks"][kk]
                        vals.append(x["v"])
                        if x["n"] < k:
                            short += 1
                            zero += x["n"] == 0
                        if x["act"] is not None:
                            acts.append(x["act"])
                        if svals is not None:
                            for t in SENS:
                                svals[str(t)].append(r["by_tie"][str(t)][kk][m]["v"])
                    if vals:
                        per_seed.append(statistics.mean(vals))
                    if acts:
                        per_seed_act.append(statistics.mean(acts))
                    if svals is not None and vals:
                        for t in SENS:
                            sens_means[str(t)].append(statistics.mean(svals[str(t)]))
                e = {"value": msd(per_seed), "n_condition_runs": runs, "n_short": short,
                     "n_zero_candidates": zero}
                if short:
                    e["actual_denominator"] = msd(per_seed_act)
                if sens_means is not None and per_seed:
                    ms = [statistics.mean(v) for v in sens_means.values() if v]
                    e["tie_seed_sensitivity_mean"] = {"min": round(min(ms), 4), "max": round(max(ms), 4)}
                tab[m] = e
            res[unit][kk] = tab
        # 같은 단위(고유 라벨)의 짝지은 차이
        pair = {}
        for base in BASELINES:
            d = {}
            for s, recs in store.items():
                for c, r in recs.items():
                    if r.get("silent") or not is_existing(c):
                        continue
                    x = r["by_tie"][str(PRIMARY)][kk]
                    if base in x:
                        d.setdefault(s, {})[c] = x["aida_current_unique"]["v"] - x[base]["v"]
            ps = paired_summary(d)
            pair[base] = {key: ps[key] for key in ("mean", "sd_across_seeds", "exploratory_t95",
                                                   "seeds_positive", "conditions_positive")}
        res["paired_unique_current_minus_baseline"][kk] = pair
        # IoU 0
        gt = tot = 0
        for s, recs in store.items():
            for c, r in recs.items():
                if r.get("silent") or not is_existing(c):
                    continue
                tot += 1
                gt += r["ks"][kk] > r["info"]["n_iou0"]
        res["iou0"][kk] = {"condition_runs_k_gt_n_iou0": gt, "n_condition_runs": tot}
        n_runs = tot
    seeds = sorted(store)
    conds = sorted({c for s in seeds for c in store[s] if is_existing(c)})
    res["iou0"]["n_iou0_by_condition"] = {
        c: [store[s][c]["info"]["n_iou0"] for s in seeds if c in store[s]] for c in conds}
    res["iou0"]["k_by_condition"] = {
        c: {kk: [store[s][c]["ks"][kk] for s in seeds if c in store[s] and "ks" in store[s][c]]
            for kk in K_KEYS} for c in conds}
    res["iou0"]["seed_order"] = seeds
    res["n_existing_condition_runs"] = n_runs
    return res


def section_c(store: dict, rank_fix: dict | None) -> dict:
    """전 조건(silent 제외, missing_* 포함 — rank_fix와 같은 조건 집합)에서 legacy → current."""
    per_seed = {}
    for s, recs in store.items():
        act = [r for r in recs.values() if not r.get("silent")]
        if not act:
            continue
        lk = statistics.mean(r["by_tie"][str(PRIMARY)]["f10"]["aida_legacy"]["v"] for r in act)
        ck = statistics.mean(r["by_tie"][str(PRIMARY)]["f10"]["aida_current"]["v"] for r in act)
        l5 = statistics.mean(r["at5"]["aida_legacy"] for r in act)
        c5 = statistics.mean(r["at5"]["aida_current"] for r in act)
        per_seed[s] = {"n_conditions": len(act), "legacy_at_k": round(lk, 4), "current_at_k": round(ck, 4),
                       "diff_at_k": round(ck - lk, 4), "legacy_at5": round(l5, 4),
                       "current_at5": round(c5, 4), "diff_at5": round(c5 - l5, 4)}
        if rank_fix and str(s) in rank_fix:
            rf = rank_fix[str(s)]
            per_seed[s]["rank_fix_before_at5"] = round(rf["before"]["5"], 4)
            per_seed[s]["rank_fix_before_at5_equals_legacy_at5"] = abs(rf["before"]["5"] - l5) < 1e-9
            per_seed[s]["rank_fix_after_at5_intermediate_order"] = round(rf["after"]["5"], 4)
    return {"per_seed": {str(s): v for s, v in sorted(per_seed.items())},
            "diff_at_k": msd([v["diff_at_k"] for v in per_seed.values()]),
            "diff_at5": msd([v["diff_at5"] for v in per_seed.values()]),
            "legacy_at_k": msd([v["legacy_at_k"] for v in per_seed.values()]),
            "current_at_k": msd([v["current_at_k"] for v in per_seed.values()]),
            "legacy_at5": msd([v["legacy_at5"] for v in per_seed.values()]),
            "current_at5": msd([v["current_at5"] for v in per_seed.values()])}


# ---------------------------------------------------------------- 재현 대조
def reproduce(store: dict, ref_ruler: dict) -> dict:
    """tieseed 파일(표 6 근거)의 조건별 값·층 평균과 같은지."""
    cond_ok = cond_tot = 0
    bad = []
    for s, recs in store.items():
        ref = {x["condition"]: x for x in ref_ruler["seeds"].get(str(s), {}).get("per_condition", [])}
        for c, r in recs.items():
            cond_tot += 1
            mine = r["stage2_primary"]
            x = ref.get(c)
            same = (x is not None and x.get("k") == mine.get("k")
                    and {k: round(v, 4) for k, v in mine.get("methods", {}).items()} == x.get("methods", {}))
            if r.get("silent"):
                same = x is not None and "k" not in x
            cond_ok += same
            if not same:
                bad.append(f"{s}/{c}")
    # 층 평균(기존 라벨 층, 시드 간 평균) — tieseed 파일의 existing_label_layer와 같은 식
    layer = {}
    for m in A2.EXISTING_METHODS:
        per_seed = []
        for s, recs in store.items():
            vals = [r["stage2_primary"]["methods"][m] for c, r in recs.items()
                    if not r.get("silent") and is_existing(c) and m in r["stage2_primary"]["methods"]]
            if vals:
                per_seed.append(statistics.mean(vals))
        layer[m] = A2._msd(per_seed)
    layer_same = all(layer[m] == ref_ruler["existing_label_layer"].get(m) for m in A2.EXISTING_METHODS)
    return {"conditions_matched": cond_ok, "conditions_total": cond_tot, "mismatched": bad[:20],
            "existing_label_layer_equal": layer_same,
            "headline": {m: (layer[m] or {}).get("mean") for m in
                         ("aida_current", "all_label_objectlab", "all_label_iou",
                          "all_label_random_expected")}}


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-10-06")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--out-dir", type=Path, default=HERE / "planning_evidence")
    a = ap.parse_args()
    pe = a.out_dir
    out_main = pe / f"controlled_baseline_followup_{a.date}.json"
    out_comp = pe / f"controlled_baseline_followup_completeness_{a.date}.json"
    for p in (out_main, out_comp):
        if p.exists():
            sys.exit(f"refuse to overwrite existing file: {p.name}")
    sys.stdout.reconfigure(encoding="utf-8")
    root = a.root
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
                          text=True).stdout.strip()
    tieseed = json.loads(TIESEED_JSON.read_text(encoding="utf-8"))
    rank_fix = {}
    for s in (42, 123, 2024):
        p = HERE / f"rank_fix_seed{s}.json"
        if p.exists():
            for row in json.loads(p.read_text(encoding="utf-8"))["rows"]:
                rank_fix.setdefault(row["kind"], {})[str(s)] = row

    file_hashes, exclusions, comp_groups = [], [], {}
    stores = {}
    totals = {"expected": 0, "present": 0, "missing": 0, "read_failed": 0, "missing_fields": 0,
              "length_or_summary_mismatch_runs": 0, "finding_label_id_breaks_rows": 0,
              "finding_label_id_breaks_runs": 0, "finding_type_mismatch_rows": 0,
              "labels_without_objectlab_score": 0}
    for g, (rulers, seeds) in EXPECTED.items():
        meta_p = root / g / "run_meta.json"
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        file_hashes.append((f"{g}/run_meta.json", sha256_file(meta_p)))
        conds = meta["conditions"]
        gcomp = {"n_conditions_run_meta": len(conds),
                 "n_conditions_expected": EXPECTED_N_CONDITIONS[g], "rulers": {}}
        if len(conds) != EXPECTED_N_CONDITIONS[g]:
            # 조건 목록 자체가 줄면 파일 단위 검사로는 누락이 안 보인다 — 따로 센다.
            totals["condition_count_mismatch_groups"] = (
                totals.get("condition_count_mismatch_groups", 0) + 1)
            gcomp["condition_count_mismatch"] = True
        for ru in rulers:
            rcomp = {}
            for s in seeds:
                sdir = root / g / ru / f"s{s}"
                summ = None
                sp = sdir / "summary.json"
                if sp.exists():
                    summ = json.loads(sp.read_text(encoding="utf-8"))
                    file_hashes.append((f"{g}/{ru}/s{s}/summary.json", sha256_file(sp)))
                scomp = {"summary_json": summ is not None, "missing": [], "read_failed": [],
                         "missing_fields": {}, "length_or_summary_mismatch": {},
                         "finding_label_id_breaks": 0, "finding_type_mismatch": 0,
                         "labels_without_objectlab_score": 0}
                for c in conds:
                    totals["expected"] += 1
                    f = sdir / f"{c}.json.gz"
                    run_id = f"{g}/{ru}/s{s}/{c}"
                    if not f.exists():
                        totals["missing"] += 1
                        scomp["missing"].append(c)
                        exclusions.append({"run": run_id, "reason": "missing file"})
                        continue
                    totals["present"] += 1
                    file_hashes.append((f"{g}/{ru}/s{s}/{c}.json.gz", sha256_file(f)))
                    try:
                        with gzip.open(f, "rt", encoding="utf-8") as fh:
                            rec = json.load(fh)
                    except Exception as exc:  # noqa: BLE001
                        totals["read_failed"] += 1
                        scomp["read_failed"].append(c)
                        exclusions.append({"run": run_id, "reason": f"read failed: {type(exc).__name__}"})
                        continue
                    chk = check_record(rec, c, summ)
                    if chk.get("missing_fields"):
                        totals["missing_fields"] += 1
                        scomp["missing_fields"][c] = chk["missing_fields"]
                        exclusions.append({"run": run_id, "reason": "missing fields",
                                           "fields": chk["missing_fields"]})
                        continue
                    if chk.get("length_or_summary_mismatch"):
                        totals["length_or_summary_mismatch_runs"] += 1
                        scomp["length_or_summary_mismatch"][c] = chk["length_or_summary_mismatch"]
                    totals["finding_label_id_breaks_rows"] += chk["finding_label_id_breaks"]
                    totals["finding_label_id_breaks_runs"] += chk["finding_label_id_breaks"] > 0
                    totals["finding_type_mismatch_rows"] += chk["finding_type_vs_label_index_mismatch"]
                    totals["labels_without_objectlab_score"] += chk["labels_without_objectlab_score"]
                    scomp["finding_label_id_breaks"] += chk["finding_label_id_breaks"]
                    scomp["finding_type_mismatch"] += chk["finding_type_vs_label_index_mismatch"]
                    scomp["labels_without_objectlab_score"] += chk["labels_without_objectlab_score"]
                    # 무결성 문제가 있는 실행은 집계에 넣지 않는다 — 그 실행만 빼고 계속한다(사용자 지시).
                    problems = [name for name, bad in (
                        ("length_or_summary_mismatch", bool(chk.get("length_or_summary_mismatch"))),
                        ("finding_label_id_breaks", chk["finding_label_id_breaks"] > 0),
                        ("finding_type_mismatch", chk["finding_type_vs_label_index_mismatch"] > 0))
                        if bad]
                    if problems:
                        exclusions.append({"run": run_id, "reason": "integrity", "problems": problems})
                        continue
                    stores.setdefault((g, ru), {}).setdefault(s, {})[c] = compact_record(rec)
                    del rec
                rcomp[str(s)] = {k: v for k, v in scomp.items()
                                 if isinstance(v, bool) or v not in ([], {}, 0)}
                print(g, ru, s, "ok", flush=True)
            gcomp["rulers"][ru] = rcomp
        comp_groups[g] = gcomp
    lp = root / "progress.log"
    if lp.exists():
        file_hashes.append(("progress.log", sha256_file(lp)))
    file_hashes.sort()
    listing = "\n".join(f"{p}  {h}" for p, h in file_hashes)
    inputs = {"raw_root": "experiment/controlled_baseline_stage2",
              "raw_files_hashed": len(file_hashes),
              "raw_files_listing_sha256": hashlib.sha256(listing.encode("utf-8")).hexdigest(),
              "raw_files_listing_format": "sorted lines '<relative path>  <sha256>' joined by \\n",
              "tieseed_json": "experiment/planning_evidence/controlled_baseline_stage2_tieseed_2026-10-06.json",
              "tieseed_json_sha256": sha256_file(TIESEED_JSON)}
    for s in (42, 123, 2024):
        p = HERE / f"rank_fix_seed{s}.json"
        if p.exists():
            inputs[f"rank_fix_seed{s}_sha256"] = sha256_file(p)

    # 재현 대조(표 6)
    repro = {}
    for (g, ru), store in stores.items():
        repro[f"{g}/{ru}"] = reproduce(store, tieseed["groups"][g]["rulers"][ru])
    reproduced = (all(v["conditions_matched"] == v["conditions_total"] and v["existing_label_layer_equal"]
                      for v in repro.values())
                  and len(repro) == sum(len(r) for r, _ in EXPECTED.values())
                  and not totals.get("condition_count_mismatch_groups"))
    totals["expected_runs_by_spec"] = 1023
    completeness = {
        "purpose": "controlled baseline follow-up, section 0: raw-record completeness and table 6 "
                   "reproduction (tie seed 20260929, same k) before any new aggregation",
        "plan": "docs/paper/controlled-baseline-followup-plan.md",
        "git_head_at_analysis": head,
        "inputs": inputs,
        "required_fields": {"rows.<ordering>": ["verdicts_by_rank", "finding_ids_by_rank", "tp", "flagged"],
                            f"rows.{CUR}": ["present_types"],
                            "population": ["all_labels[image,label_index,label_iou,injected_error]",
                                           "unmatched_predictions[image,box,confidence,matches_dropped]",
                                           "objectlab.available"]},
        "checks": {"length": "len(verdicts) == len(finding_ids) == flagged; sum(verdict) == tp; "
                             "legacy/current same finding-id multiset; objectlab.labels_scored == "
                             "labels with objectlab_score",
                   "summary": "summary.json per_condition (P@10%, both orderings) == recomputed; "
                              "silent listed",
                   "finding_label_id_breaks": "findings with a label index whose (image, label_index) "
                                              "is not in population.all_labels",
                   "finding_type_mismatch": "'missing' finding with a label index or non-missing "
                                            "finding without one"},
        "totals": totals,
        "exclusions": exclusions,
        "groups": comp_groups,
        "table6_reproduction": {"rule": "per condition: k and 4-decimal methods equal to tieseed "
                                        "per_condition; per ruler: existing_label_layer mean/sd equal",
                                "reproduced": reproduced, "by_ruler": repro},
    }
    if not reproduced:
        completeness["stopped"] = "table 6 values not reproduced from raw records — no A/B/C analysis"
    out_comp.write_text(json.dumps(completeness, ensure_ascii=False, indent=1), encoding="utf-8")
    print("completeness:", json.dumps(totals), "excl", len(exclusions), "reproduced", reproduced)
    if not reproduced:
        out_main.write_text(json.dumps({"stopped": completeness["stopped"],
                                        "completeness_file": out_comp.name,
                                        "git_head_at_analysis": head, "inputs": inputs},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
        return

    result = {
        "purpose": "controlled baseline follow-up (plan sections A/B/C) — re-aggregation of stored raw "
                   "records only; no re-inference, no training, no GPU",
        "plan": "docs/paper/controlled-baseline-followup-plan.md",
        "spec": "docs/paper/controlled-baseline-spec.md",
        "synthetic": "injected errors on KITTI/COCO subsets; ground truth = injection record; not "
                     "human-adjudicated; pre-existing label errors count as non-errors",
        "git_head_at_analysis": head,
        "inputs": inputs,
        "completeness_file": f"experiment/planning_evidence/{out_comp.name}",
        "completeness_totals": totals,
        "exclusions": exclusions,
        "table6_reproduced": reproduced,
        "rules": {
            "layer": "existing-label layer = non-silent conditions excluding missing_* (A, B); "
                     "C uses all non-silent conditions incl. missing_* (same set as rank_fix_seed*.json)",
            "k_primary": "k = max(1, floor(0.10 * AIDA findings)) — same k as table 6",
            "denominator": "k (user-confirmed); n_short = condition runs with candidates < k; "
                           "actual_denominator = min(k, candidates) variant (0-candidate runs excluded)",
            "random_expected": "rate * min(k, candidates) / k",
            "tie_rule": "ascending sha256(f'{tie_seed}:{candidate_id}'); primary 20260929; sensitivity "
                        "1..10 reported separately, never pooled with training seeds",
            "aggregation": "per condition per training seed -> per-seed condition mean -> mean across "
                           "seeds; conditions fixed (not resampled)",
            "interval": "exploratory 95% t interval over per-seed means, df = seeds - 1; none for "
                        "single-seed groups (C, D). An interval excluding 0 is not a superiority claim",
            "positives": "seeds_positive = seeds whose condition-mean difference > 0; "
                         "conditions_positive = conditions whose seed-mean difference > 0",
            "units": {"finding": FINDING_UNIT, "unique_label": UNIQUE_UNIT},
            "k_series": {"findings_pct": FINDING_PCTS, "labels_pct": LABEL_PCTS,
                         "keys": "f<p> = p% of AIDA findings, l<p> = p% of all in-scope labels"},
            "iou0": "label_iou == 0 labels are kept; per condition counts and k > n_iou0 recorded",
            "at5": "@5 = precision of the top 5 findings (evaluate_box_accuracy.precision_at_k, "
                   "denominator min(5, findings)); @k = P@10% with denominator k. Different metrics.",
        },
        "A_paired_differences": {}, "B_k_sensitivity": {}, "C_plus041_replacement_material": {},
    }
    for (g, ru), store in stores.items():
        key = f"{g}/{ru}"
        result["A_paired_differences"][key] = section_a(store)
        result["B_k_sensitivity"][key] = section_b(store)
        result["C_plus041_replacement_material"][key] = section_c(store, rank_fix.get(ru) if g == "A" else None)
        result["A_paired_differences"][key]["current_unique_equals_current_f10_runs"] = (
            f"{sum(r.get('current_unique_equals_current_f10', True) for s in store.values() for r in s.values())}"
            f"/{sum(len(s) for s in store.values())}")
    result["C_plus041_replacement_material"]["_note"] = (
        "The original +0.41 averaged 5 misaligned rulers (broad bicycle-0/mid/rich, shifted, broad) and "
        "compared legacy with an intermediate absolute-threshold order. The 3 broad-bicycle rulers are not "
        "in the stage-2 rerun, so that composition cannot be replicated; values here are legacy -> "
        "review_order_v1 per stored ruler. @k and @5 are different metrics. Draft text is not changed.")
    out_main.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for key, v in result["A_paired_differences"].items():
        print(key, {b: (e["primary_tie_seed"]["mean"], e["primary_tie_seed"]["exploratory_t95"],
                        e["primary_tie_seed"]["seeds_positive"], e["primary_tie_seed"]["conditions_positive"])
                    for b, e in v.items() if isinstance(e, dict)})


if __name__ == "__main__":
    main()
