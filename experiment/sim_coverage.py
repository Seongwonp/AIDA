"""합성 자료로 미판정 처리 방식의 구간 포함률과 치우침을 잰다 (논문 P5, val을 열지 않는다).

`sim_unjudged.py`의 생성 과정(참값이 있다)을 초모집단으로 두고 데이터셋을 여러 번 새로 뽑는다.

| 처리 | 무엇 |
|---|---|
| `unjudged_zero` | 원래 판정 범위(방법별 상위 N 합집합 ∪ K)만 판정, 재표본에 끼어든 미판정은 수확 0 (옛 코드 동작) |
| `fixed_union` | 고정 재표본 합집합을 전량 판정 — 모든 재표본의 상위 N이 판정되므로 전량 판정과 같은 구간이 나온다 (사전 등록 안 (a)) |

**추정 대상 θ.** 같은 생성 과정·같은 크기의 데이터셋에서 N=90 고유 오류 수 차이(기준선 − aida)의 기댓값.
`--theta-reps`개 데이터셋의 전량 판정 관측 차이 평균으로 근사한다. 포함률은 각 처리의 95% 백분위 구간이 θ를
포함한 비율이다.

**조건(`--scenario`)**

| 이름 | 무엇 |
|---|---|
| `base` | `sim_unjudged.py` 기본값 — 기록 35개, 기록당 6~10장 |
| `qa_like` | 사전 등록 D3와 같은 모양 — 기록 30개 × 10장 = 300장 |
| `low_error` | 기본값에서 라벨 오류 확률 × 0.5 |
| `high_error` | 기본값에서 라벨 오류 확률 × 1.5 |

**숫자는 합성이다.** 한 가지 생성 과정의 예시이며 실제 nuImages 값이 아니다. 결과:
`planning_evidence/sim_coverage_<scenario>_<날짜>.json` (`synthetic: true`). 반복이 끝날 때마다 진행률과 남은 시간을
찍고, 20회마다 `.partial.json`으로 중간 저장한다.

    python sim_coverage.py --scenario base --reps 10 --iters 2000   # 먼저 시간 재기
    python sim_coverage.py --scenario base                          # 본 실행 (반복 200, 부트스트랩 2000)
    python sim_coverage.py --scenario all                           # 네 조건을 차례로
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim_unjudged as S  # noqa: E402
from evaluation.bootstrap import paired_cluster_bootstrap  # noqa: E402
from evaluation.ranking import top_n  # noqa: E402
from evaluation.summary import summarise  # noqa: E402

THETA_SEED0 = 100_000
REP_SEED0 = 1_000
BASELINES = (S.IOU, S.OL)
SCENARIOS = {
    "base": {},
    "qa_like": {"n_logs": 30, "imgs_per_log": (10, 10)},
    "low_error": {"err_scale": 0.5},
    "high_error": {"err_scale": 1.5},
}


def _dataset(seed: int, params: dict):
    rows, truth, s_iou, s_ol, in_aida = S.make_population(seed, **params)
    rankings = S.rankings_for(rows, s_iou, s_ol, in_aida)
    by_key = {a.key: a for a in rows}
    tops = {m: {r.candidate_key for r in top_n([r for r in rankings if r.method == m], by_key, S.N)}
            for m in (S.AIDA, S.IOU, S.OL)}
    outside = sorted(a.key for a in rows if a.key not in in_aida)
    judged = set().union(*tops.values()) | set(random.Random(S.K_SEED).sample(outside, min(S.K, len(outside))))
    partial = S.with_verdicts(rows, truth, judged)
    oracle = S.with_verdicts(rows, truth, set(by_key))
    return rankings, partial, oracle


def theta_one(args: tuple[int, dict]) -> dict:
    seed, params = args
    rankings, _partial, oracle = _dataset(seed, params)
    y = {m: summarise(oracle, rankings, m, S.N).unique_error_yield for m in (S.AIDA, S.IOU, S.OL)}
    return {b: y[b] - y[S.AIDA] for b in BASELINES}


def rep_one(args: tuple[int, int, dict]) -> dict:
    seed, iters, params = args
    t0 = time.time()
    rankings, partial, oracle = _dataset(seed, params)
    out = {}
    for b in BASELINES:
        res = {}
        for name, adj in (("unjudged_zero", partial), ("fixed_union", oracle)):
            r = paired_cluster_bootstrap(adj, rankings, b, S.AIDA, S.N, iters, S.BOOT_SEED,
                                         require_same_candidates=False)
            res[name] = {"observed": r["observed_difference"], "lo": r["ci_low"], "hi": r["ci_high"]}
        out[b] = res
    return {"seed": seed, "seconds": round(time.time() - t0, 1), "by_baseline": out}


def summarise_reps(reps: list[dict], theta: dict) -> dict:
    table = {}
    for b in BASELINES:
        t = theta[b]
        row = {}
        for name in ("unjudged_zero", "fixed_union"):
            cis = [r["by_baseline"][b][name] for r in reps]
            mids = [(c["lo"] + c["hi"]) / 2 for c in cis]
            cov = sum(c["lo"] <= t <= c["hi"] for c in cis) / len(cis)
            row[name] = {
                "coverage_of_theta": round(cov, 3),
                "coverage_mc_se": round((cov * (1 - cov) / len(cis)) ** 0.5, 3),
                "mean_width": round(statistics.mean(c["hi"] - c["lo"] for c in cis), 2),
                "mean_midpoint_minus_theta": round(statistics.mean(mids) - t, 2),
                "share_ci_excludes_zero": round(sum(not (c["lo"] <= 0 <= c["hi"]) for c in cis) / len(cis), 3),
            }
        diffs = [r["by_baseline"][b]["unjudged_zero"] != r["by_baseline"][b]["fixed_union"] for r in reps]
        row["share_reps_where_intervals_differ"] = round(sum(diffs) / len(reps), 3)
        table[f"{b} - {S.AIDA}"] = {"theta": round(t, 3), **row}
    return table


def _log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def run_scenario(name: str, a) -> Path:
    params = SCENARIOS[name]
    stamp = dt.date.today().isoformat()
    out_path = Path(a.out_dir) / f"sim_coverage_{name}_{stamp}.json"
    partial_path = out_path.with_suffix(".partial.json")
    settings = {"scenario": name, "scenario_params": {k: list(v) if isinstance(v, tuple) else v
                                                      for k, v in params.items()},
                "N": S.N, "K": S.K, "bootstrap_iterations": a.iters, "bootstrap_seed": S.BOOT_SEED,
                "tie_seed": S.TIE_SEED, "replicates": a.reps, "rep_seed_start": REP_SEED0,
                "theta_replicates": a.theta_reps, "theta_seed_start": THETA_SEED0,
                "difference_sign": "baseline - aida", "interval": "95% percentile, paired log-cluster"}

    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        _log(f"{name}: θ 추정 {a.theta_reps}개 데이터셋")
        th = list(ex.map(theta_one, [(THETA_SEED0 + i, params) for i in range(a.theta_reps)], chunksize=50))
        theta = {b: statistics.mean(x[b] for x in th) for b in BASELINES}
        theta_sd = {b: statistics.stdev(x[b] for x in th) for b in BASELINES}
        _log(f"{name}: θ = " + ", ".join(f"{b}−aida {theta[b]:.2f}" for b in BASELINES))

        futs = [ex.submit(rep_one, (REP_SEED0 + i, a.iters, params)) for i in range(a.reps)]
        reps, t0 = [], time.time()
        for k, f in enumerate(as_completed(futs), 1):
            reps.append(f.result())
            el = time.time() - t0
            eta = el / k * (a.reps - k)
            _log(f"{name}: {k}/{a.reps} ({100 * k / a.reps:.0f}%) 경과 {el / 60:.1f}분, 남은 시간 약 {eta / 60:.1f}분")
            if k % 20 == 0 and k < a.reps:
                partial_path.write_text(json.dumps({"synthetic": True, "partial": True, "settings": settings,
                                                    "done": k, "replicates": reps}, ensure_ascii=False),
                                        encoding="utf-8")

    reps.sort(key=lambda r: r["seed"])
    out = {
        "synthetic": True,
        "note": "합성 자료. sim_unjudged.py 생성 과정의 한 조건이며 실제 데이터의 값이 아니다.",
        "settings": settings,
        "theta": {f"{b} - {S.AIDA}": {"mean": round(theta[b], 3), "sd_across_datasets": round(theta_sd[b], 3)}
                  for b in BASELINES},
        "summary": summarise_reps(reps, theta),
        "replicates": reps,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    partial_path.unlink(missing_ok=True)
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1), flush=True)
    _log(f"→ {out_path}")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="base", choices=[*SCENARIOS, "all"])
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--theta-reps", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "planning_evidence"))
    a = ap.parse_args()
    for name in (SCENARIOS if a.scenario == "all" else [a.scenario]):
        run_scenario(name, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
