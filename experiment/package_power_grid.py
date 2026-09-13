"""검정력 격자 결과를 **다시 읽을 수 있는 산출물**로 묶는다 (docs/n-required-plan.md 8절).

Markdown 표만 있으면 숫자를 다시 쓸 수 없고, 어느 코드·시나리오·씨앗으로 나왔는지도
모른다. 그래서 원시 JSON을 그대로 옮기고, 옆에 CSV와 출처 명세(manifest)를 둔다.

**원시 결과는 고치지 않는다.** 행마다 덧붙이는 것은 결과에서 결정적으로 계산되는
값뿐이다 — 칸 씨앗(규칙으로 복원), 성공 횟수, Wilson 95% 구간, 탐색 표시.

    ./venv/Scripts/python.exe package_power_grid.py --raw <power_report --out JSON> \\
        --name power_grid_explore_2026-09-13 --code-commit 159d04d8 \\
        --scenario-commit 159d04d8 --runtime-minutes 64.6 \\
        --command "power_report.py --total-minutes 30 60 120 180 --allow-long" \\
        --hardware "Intel Core i5-14400 (10 cores / 16 threads), workers 15"
"""
import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

from evaluation.planning import wilson_interval  # noqa: E402
OUT_DIR = HERE / "planning_evidence"
SCENARIO_PATH = "experiment/planning_scenarios.json"

# evaluation/planning.py의 공식 최소. 가져오지 않고 적는 이유: 이 산출물은 **만들어진
# 시점의 기준**을 담아야 한다 — 나중에 기준이 바뀌어도 옛 결과의 표시가 바뀌면 안 된다.
OFFICIAL_ITERATIONS = 200
OFFICIAL_BOOTSTRAP = 400


def wilson(k: int, n: int) -> tuple[float, float]:
    """이항 비율의 95% Wilson 구간. **성공 0회·전부 성공에서도 폭이 0이 아니다.**

    식은 `evaluation.planning.wilson_interval` 하나만 둔다.
    """
    return wilson_interval(k, n)


def cell_seed(random_seed: int, row: dict) -> str:
    """power_report가 칸마다 쓰는 씨앗 규칙: `f"{random_seed}|{scenario.name}"`."""
    name = (f"D{row['datasets']}_N{row['budget']}_p{row['prevalence']}_"
            f"{row['dependence']}_{row['ranking']}")
    return f"{random_seed}|{name}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_scenario_blob(commit: str) -> bytes:
    """만들어진 시점의 시나리오 파일을 커밋에서 그대로 읽는다.

    얕은 복제(CI 기본값)에는 옛 커밋이 없다. `check=True`의 CalledProcessError는
    원인을 안 알려주므로 무엇을 하면 되는지 적어 준다.
    """
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{SCENARIO_PATH}"],
                          capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"시나리오 파일을 커밋에서 읽지 못했다: {commit}:{SCENARIO_PATH}\n"
            "얕은 복제에는 옛 커밋이 없다 — `git fetch --unshallow` 뒤 다시 돌린다.\n"
            f"git: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def package(raw: dict, *, random_seed: int, iterations: int, bootstrap: int) -> list[dict]:
    rows = []
    for row in raw["rows"]:
        out = dict(row)
        out["cell_seed"] = cell_seed(random_seed, row)
        out["exploratory"] = True
        out["official_iteration_requirement_met"] = (
            iterations >= OFFICIAL_ITERATIONS and bootstrap >= OFFICIAL_BOOTSTRAP)
        deltas = []
        for d in row["deltas"]:
            k = round(d["power"] * iterations)
            if abs(k / iterations - d["power"]) > 1e-9:
                raise ValueError(f"검정력이 복제 수로 떨어지지 않는다: {d['power']} × {iterations}")
            low, high = wilson(k, iterations)
            deltas.append({**d, "successes": k, "iterations": iterations,
                           "power_wilson95_low": round(low, 4),
                           "power_wilson95_high": round(high, 4)})
        out["deltas"] = deltas
        rows.append(out)
    return rows


CSV_FIELDS = ["prevalence", "dependence", "ranking", "aida_auc", "baseline_auc",
              "datasets", "budget", "pool", "images", "delta_name", "delta",
              "successes", "iterations", "power", "monte_carlo_se",
              "power_wilson95_low", "power_wilson95_high",
              "exceeds_expected_errors", "pool_unique_errors_per_dataset",
              "mean_aida_unique_errors", "mean_baseline_unique_errors",
              "blocks_per_dataset", "blocks_total", "per_dataset_evidence", "evidence",
              "required_active_minutes", "status", "official_scenario", "exploratory",
              "cell_seed"]


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        for d in row["deltas"]:
            writer.writerow({**{k: row.get(k) for k in CSV_FIELDS},
                             "delta_name": d["name"], "delta": d["delta"],
                             "successes": d["successes"], "iterations": d["iterations"],
                             "power": d["power"], "monte_carlo_se": d["monte_carlo_se"],
                             "power_wilson95_low": d["power_wilson95_low"],
                             "power_wilson95_high": d["power_wilson95_high"],
                             "exceeds_expected_errors": d["exceeds_expected_errors"]})
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="검정력 격자 산출물 묶기")
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--scenario-commit", required=True)
    parser.add_argument("--runtime-minutes", required=True, type=float)
    parser.add_argument("--command", required=True)
    parser.add_argument("--hardware", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    # 덮어쓰기 검사를 **일하기 전에** 한다. 뒤에 두면 셋 중 하나만 있을 때
    # 나머지를 쓰고 나서 멈춰 반쪽 산출물이 남는다.
    json_path = OUT_DIR / f"{args.name}.json"
    csv_path = OUT_DIR / f"{args.name}.csv"
    manifest_path = OUT_DIR / f"{args.name}.manifest.json"
    for path in (json_path, csv_path, manifest_path):
        if path.exists():
            raise SystemExit(f"이미 있다 — 덮어쓰지 않는다: {path}")

    raw_bytes = args.raw.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    scenario_bytes = read_scenario_blob(args.scenario_commit)
    scenario = json.loads(scenario_bytes.decode("utf-8"))
    random_seed = scenario["grid"]["random_seed"]["value"]
    iterations, bootstrap = raw["iterations"], raw["bootstrap_iterations"]

    rows = package(raw, random_seed=random_seed, iterations=iterations, bootstrap=bootstrap)
    packaged = {
        "name": args.name,
        "exploratory": True,
        "status_note": ("탐색 실행이다. 복제·재표집이 공식 최소에 못 미쳐 모든 칸이 "
                        "too_few_iterations이고, 순위 품질 가정이 근거 없어 모든 칸이 "
                        "official=False다. N_required의 근거가 아니다."),
        "iterations": iterations, "bootstrap_iterations": bootstrap,
        "official_minimum": {"iterations": OFFICIAL_ITERATIONS, "bootstrap_iterations": OFFICIAL_BOOTSTRAP},
        "n_required_status": "undetermined", "n_final_status": "undetermined",
        "delta_status": "undetermined",
        "rows": rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(packaged, ensure_ascii=False, indent=2) + "\n"
    csv_text = to_csv(rows)
    json_path.write_text(json_text, encoding="utf-8")
    csv_path.write_text(csv_text, encoding="utf-8")

    manifest = {
        "name": args.name,
        "generated_by": "experiment/power_report.py (결과), experiment/package_power_grid.py (묶음)",
        "command": args.command,
        "code_commit": args.code_commit,
        "scenario_file": "experiment/planning_scenarios.json",
        "scenario_commit": args.scenario_commit,
        "scenario_sha256": sha256_bytes(scenario_bytes),
        "random_seed": random_seed,
        "cell_seed_rule": "f\"{random_seed}|D{D}_N{N}_p{prevalence}_{dependence}_{ranking}\"",
        "iterations": iterations,
        "bootstrap_iterations": bootstrap,
        "cells": len(rows),
        "runtime_minutes_wall": args.runtime_minutes,
        "hardware": args.hardware,
        "raw_output_sha256": sha256_bytes(raw_bytes),
        "packaged_json": json_path.name,
        "packaged_json_sha256": sha256_bytes(json_text.encode("utf-8")),
        "packaged_csv": csv_path.name,
        "packaged_csv_sha256": sha256_bytes(csv_text.encode("utf-8")),
        "note": args.note,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("raw_output_sha256", "packaged_json_sha256",
                                                "packaged_csv_sha256", "scenario_sha256")},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
