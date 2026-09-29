"""합성 자료로 미판정 후보 문제와 추가 판정량을 재는 시뮬레이션 (val을 열지 않는다).

원본(저장소 밖 `sim_unjudged.py`, 2026-09-27)과 다른 점 — Codex 검토 반영:

| 항목 | 원본 | 이 파일 |
|---|---|---|
| 동점 키 | Python `hash()` (프로세스마다 다름) | 백엔드와 같은 `sha256("{tie_seed}:{후보 id}")` |
| 무작위 K | 전체 라벨에서 | **AIDA 규칙 밖 라벨**에서 (실제 `_mark_random_sample`) |
| 방법 | aida·all_label_iou 둘 | aida(v2)·all_label_iou·all_label_objectlab **셋**의 상위 N 합집합 ∪ K |
| 차이 부호 | aida − 기준선 | **기준선 − aida** (사전 등록 D7과 같음) |

**숫자는 합성이다.** 메커니즘과 추가 판정량의 크기 감만 본다. 결과는
`planning_evidence/sim_unjudged_2026-09-27.json`에 `synthetic: true`로 남긴다.

ObjectLab 모사: 라벨의 유사도 s = iou·0.9 + 0.1·(1 − 중심거리), 겹치는 예측의 확신도 ≤ 0.5이거나
IoU 0이면 badloc 1.0(깨끗). 실제 cleanlab의 alpha·문턱 기본값을 흉내 낸 것이지 cleanlab 호출이 아니다.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluation.bootstrap import iter_resamples, paired_cluster_bootstrap  # noqa: E402
from evaluation.coverage import resample_top_n_union, tie_key  # noqa: E402
from evaluation.ranking import top_n  # noqa: E402
from evaluation.schema import Adjudication, Ranking  # noqa: E402
from evaluation.summary import summarise  # noqa: E402

N, K, ITER, BOOT_SEED = 90, 50, 2000, 42
TIE_SEED, K_SEED = 20260929, 20260928
AIDA, IOU, OL = "aida", "all_label_iou", "all_label_objectlab"


def make_population(seed, n_logs=35, imgs_per_log=(6, 10), labels_per_img=(2, 6), keep_rate=0.45, err_scale=1.0):
    rng = random.Random(seed)
    rows, truth, score_iou, score_ol, in_aida = [], {}, {}, {}, set()
    for g in range(n_logs):
        for i in range(rng.randint(*imgs_per_log)):
            img = f"log{g:02d}_img{i}"
            for l in range(rng.randint(*labels_per_img)):
                iou = 0.0 if rng.random() < 0.10 else min(1.0, max(0.0, rng.gauss(0.82, 0.13)))
                s = 1 - iou
                p_err = min(0.95, err_scale * (0.35 if iou == 0.0 else min(0.9, 0.02 + 1.6 * s ** 2)))
                a = Adjudication("d", img, f"L{l}", "box", label_index=l, group_id=f"log{g:02d}")
                rows.append(a)
                truth[a.key] = rng.random() < p_err
                score_iou[a.key] = round(s, 4)
                conf = rng.uniform(0.3, 0.99)
                centre = rng.uniform(0.0, 0.3)
                if iou == 0.0 or conf <= 0.5:
                    score_ol[a.key] = 0.0                       # badloc 1.0 → 우선순위 0
                else:
                    score_ol[a.key] = round(1 - (iou * 0.9 + 0.1 * (1 - centre)), 4)
                if rng.random() < (keep_rate + 0.3 * s):
                    in_aida.add(a.key)
    return rows, truth, score_iou, score_ol, in_aida


def rankings_for(rows, score_iou, score_ol, in_aida):
    out = []
    for a in rows:
        tk = tie_key(TIE_SEED, a.candidate_id + "@" + a.image_id)   # 후보마다 하나, 방법 간 공유
        out.append(Ranking(IOU, a.key, score_iou[a.key], tie_key=tk))
        out.append(Ranking(OL, a.key, score_ol[a.key], tie_key=tk))
        if a.key in in_aida:
            out.append(Ranking(AIDA, a.key, score_iou[a.key], tie_key=tk))   # v2: 1 − label_iou
    return out


def with_verdicts(rows, truth, judged):
    return [replace(a, verdict=("hit" if truth[a.key] else "miss")) if a.key in judged else a
            for a in rows]


def run(seed) -> dict:
    rows, truth, s_iou, s_ol, in_aida = make_population(seed)
    rankings = rankings_for(rows, s_iou, s_ol, in_aida)
    by_key = {a.key: a for a in rows}
    tops = {m: {r.candidate_key for r in top_n([r for r in rankings if r.method == m], by_key, N)}
            for m in (AIDA, IOU, OL)}
    outside = sorted(a.key for a in rows if a.key not in in_aida)          # 규칙 밖 라벨
    random_k = set(random.Random(K_SEED).sample(outside, K))
    judged = set().union(*tops.values()) | random_k

    partial = with_verdicts(rows, truth, judged)
    oracle = with_verdicts(rows, truth, set(by_key))
    obs = {m: summarise(partial, rankings, m, N).unique_error_yield for m in (AIDA, IOU, OL)}
    assert obs == {m: summarise(oracle, rankings, m, N).unique_error_yield for m in obs}

    def ci(adj, base):
        r = paired_cluster_bootstrap(adj, rankings, base, AIDA, N, ITER, BOOT_SEED,
                                     require_same_candidates=False)
        return {"observed": r["observed_difference"], "ci": [r["ci_low"], r["ci_high"]],
                "unjudged_in_top_n": r["unjudged_in_top_n"]}

    coverage = resample_top_n_union(rows, rankings, [AIDA, IOU, OL], N, ITER, BOOT_SEED,
                                    judged_pool=judged)
    return {
        "seed": seed, "labels": len(rows), "aida_candidates": len(in_aida),
        "judged_pool": len(judged), "observed_yield": obs,
        "difference_sign": "baseline - aida",
        "iou_minus_aida": {"current_code": ci(partial, IOU), "oracle_all_judged": ci(oracle, IOU)},
        "objectlab_minus_aida": {"current_code": ci(partial, OL), "oracle_all_judged": ci(oracle, OL)},
        "coverage": coverage,
    }


def main() -> int:
    results = [run(seed) for seed in (1, 2, 3)]
    out = {"synthetic": True, "note": "합성 자료. 메커니즘과 추가 판정량의 크기 감만 본다. 실제 데이터의 값이 아니다.",
           "settings": {"N": N, "K": K, "iterations": ITER, "bootstrap_seed": BOOT_SEED,
                        "tie_seed": TIE_SEED, "random_sample_seed": K_SEED},
           "results": results}
    path = Path(__file__).resolve().parent / "planning_evidence" / "sim_unjudged_2026-09-27.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        c = r["coverage"]
        print(f"seed {r['seed']}: labels {r['labels']} judged {r['judged_pool']} "
              f"required {c['required_total']} (+{c['additional_beyond_pool']}) | "
              f"iou-aida current {r['iou_minus_aida']['current_code']['ci']} oracle "
              f"{r['iou_minus_aida']['oracle_all_judged']['ci']} | unjudged mean aida "
              f"{r['iou_minus_aida']['current_code']['unjudged_in_top_n'][AIDA]['mean']:.2f}")
    print("→", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
