"""통제 기준선 2단계 — 기존 가중치 재추론(학습 없음), 이어 돌리기 가능.

명세: docs/paper/controlled-baseline-spec.md. 조건마다 추론 한 번으로
legacy_severity_v0·review_order_v1 두 순서를 채점하고 모집단(전체 라벨 + label_iou +
주입 정답, 미매칭 예측, ObjectLab)을 같이 모아 `controlled_baseline_stage2/`(git 무시)에
(묶음/자/시드/조건).json.gz로 남긴다. 이미 있는 조건은 건너뛴다.

묶음마다 config가 import 시점에 환경변수로 경로를 정하므로, `--group all`은 묶음별로
자식 프로세스를 띄워 환경을 따로 준다.

  A  clean 자 4종 × 7시드 × conditions_mc_cyclist_rich 29   (4클래스, cyclist_rich)
  B  COCO 자 2종 × 3시드 × conditions_coco 26              (AIDA_DATASET=coco)
  C  self(runs_mc/<조건>) × conditions_mc 29               (4클래스, random) — 원래 eval은
     신뢰도 프로파일을 썼으나 여기서는 쓰지 않는다
  D  KITTI Car runs/clean × conditions 26                  (Car)

사용법:
  python run_controlled_baseline_stage2.py --group all
  python run_controlled_baseline_stage2.py --group A --rulers far broad --seeds 42   # 사전 대조
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_ROOT = HERE / "controlled_baseline_stage2"
ORDERINGS = ["legacy_severity_v0", "review_order_v1"]
MC4 = "Car,Van,Pedestrian,Cyclist"

GROUPS = {
    "A": {"env": {"AIDA_CLASSES": MC4, "AIDA_FRAME_SELECT": "cyclist_rich"},
          "rulers": ["matched", "shifted", "far", "broad"],
          "seeds": [42, 7, 123, 777, 2024, 2025, 31337]},
    "B": {"env": {"AIDA_DATASET": "coco"},
          "rulers": ["coco_self", "kitti_on_coco"], "seeds": [42, 123, 2024]},
    "C": {"env": {"AIDA_CLASSES": MC4}, "rulers": ["self"], "seeds": [42]},
    "D": {"env": {}, "rulers": ["kitti_car_clean"], "seeds": [42]},
}


def _child_env(group: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIDA_")}
    env.update(GROUPS[group]["env"])
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _log(line: str) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    with (OUT_ROOT / "progress.log").open("a", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")


def run_group(group: str, rulers: list[str], seeds: list[int], limit: int) -> None:
    for k in ("AIDA_RELIABILITY_PROFILE", "AIDA_RULER_WEIGHTS"):
        if os.environ.get(k):
            raise SystemExit(f"{k}가 설정돼 있다 — 2단계는 비운 상태로 돈다")
    import config
    import compare_rulers_seeded as C
    import evaluate_box_accuracy as E
    import ruler_check

    conds = [c.name for c in config.CONDITIONS]
    if config.MULTICLASS:
        conds += [c.name for c in config.CLASS_SWAP_CONDITIONS]
    conds = [c for c in conds if c != "clean"]
    C.CONDITIONS = conds

    def weights_for(ruler: str, seed: int, cond: str | None = None) -> Path:
        if group in ("A", "B"):
            return C.ruler_path(ruler, seed)
        if group == "C":
            return config.RUNS_DIR / cond / "weights" / "best.pt"
        return config.RUNS_DIR / "clean" / "weights" / "best.pt"

    meta_path = OUT_ROOT / group / "run_meta.json"
    meta = (json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists()
            else {"group": group, "env": GROUPS[group]["env"],
                  "AIDA_RELIABILITY_PROFILE": "unset", "AIDA_RULER_WEIGHTS": "unset",
                  "conditions_dir": config.CONDITIONS_DIR.name, "conditions": conds,
                  "limit": limit, "orderings": ORDERINGS, "weights_sha256": {}})
    for ruler in rulers:
        for seed in seeds:
            if group in ("A", "B"):
                w = weights_for(ruler, seed)
                meta["weights_sha256"][f"{ruler}/s{seed}"] = {
                    "path": w.relative_to(HERE).as_posix(), "sha256": ruler_check.sha256_of(w)}
                E.RULER_PATH = w
            elif group == "C":
                E.RULER_PATH, E.RULER = None, "self"
                for c in conds:
                    w = weights_for(ruler, seed, c)
                    meta["weights_sha256"][f"self/{c}"] = {
                        "path": w.relative_to(HERE).as_posix(), "sha256": ruler_check.sha256_of(w)}
            else:
                E.RULER_PATH, E.RULER = None, "clean"
                w = weights_for(ruler, seed)
                meta["weights_sha256"][f"{ruler}/s{seed}"] = {
                    "path": w.relative_to(HERE).as_posix(), "sha256": ruler_check.sha256_of(w)}
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

            store = C.ConditionStore(OUT_ROOT / group / ruler / f"s{seed}")
            t0 = time.time()

            def note(name, rec, reused, _r=ruler, _s=seed):
                if not reused:
                    _log(f"{group} {_r} s{_s} {name} done {time.time() - t0:.0f}s")

            summ = C.measure_orderings(conds, limit, ORDERINGS, collect_population=True,
                                       store=store, on_condition=note)
            (store.folder / "summary.json").write_text(
                json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
            _log(f"{group} {ruler} s{seed} FINISHED legacy_top10="
                 f"{summ['legacy_severity_v0']['top10']:.4f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, choices=[*GROUPS, "all"])
    ap.add_argument("--rulers", nargs="+")
    ap.add_argument("--seeds", type=int, nargs="+")
    ap.add_argument("--limit", type=int, default=80)
    a = ap.parse_args()
    if a.group == "all":
        for g in GROUPS:
            _log(f"group {g} start")
            env = _child_env(g)
            env["_AIDA_STAGE2_CHILD"] = g
            r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--group", g,
                                "--limit", str(a.limit)], env=env, cwd=HERE)
            if r.returncode != 0:
                _log(f"group {g} FAILED rc={r.returncode}")
                raise SystemExit(r.returncode)
        _log("ALL DONE")
        return
    # 단일 묶음: 부모 셸 환경을 쓰지 않고 그 묶음 환경으로 다시 띄운다(혼동 방지)
    if os.environ.get("_AIDA_STAGE2_CHILD") != a.group:
        env = _child_env(a.group)
        env["_AIDA_STAGE2_CHILD"] = a.group
        cmd = [sys.executable, str(Path(__file__).resolve()), "--group", a.group,
               "--limit", str(a.limit)]
        if a.rulers:
            cmd += ["--rulers", *a.rulers]
        if a.seeds:
            cmd += ["--seeds", *map(str, a.seeds)]
        raise SystemExit(subprocess.run(cmd, env=env, cwd=HERE).returncode)
    g = GROUPS[a.group]
    run_group(a.group, a.rulers or g["rulers"], a.seeds or g["seeds"], a.limit)


if __name__ == "__main__":
    main()
