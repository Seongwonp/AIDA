"""라벨 단위 진단의 정확도를 27개 조건 전체로 측정한다.

우리가 주입한 오류의 정답을 이미 알고 있으므로, 진단이 그 정답을 도로
맞히는지를 혼동행렬로 잴 수 있다 — AIDA에 지금까지 없던 "진단 정확도"라는
숫자를 만드는 것이 이 스크립트의 목적이다.

회전각 조건에 대한 주의:
  AABB에서 회전은 외접 박스를 키우는 방식으로 근사되므로, 회전 오류는
  기하학적으로 "크기 오류"와 구분되지 않는다. 어느 방향으로 커지는지는
  객체의 종횡비가 결정한다 — 폭 w, 높이 h인 박스를 θ만큼 돌리면
  외접 박스는 (w·cosθ + h·sinθ) × (w·sinθ + h·cosθ)가 되므로,
  가로로 긴 객체는 세로가, 세로로 긴 객체는 가로가 더 크게 부푼다.
  KITTI Car는 대체로 가로가 길어(예: 100x50, 15도 회전 시 세로 +48%,
  가로 +9.5%) 진단이 height로 나오는 것이 기하학적으로 정확한 답이다.
  따라서 회전은 특정 유형 하나가 아니라 "크기 계열(width/height/scale)"로
  나오면 정답으로 채점한다. 이건 진단 로직의 결함이 아니라 AABB 표현
  자체의 한계이고, OBB 실험에서 이미 실측으로 확인한 사실이다
  (docs/21 "OBB 실험 결과 요약").

사용법:
  python evaluate_label_diagnosis.py                 # 전체 조건
  python evaluate_label_diagnosis.py --limit 60      # 조건당 이미지 수 제한
"""
import argparse
import csv
import json
from pathlib import Path

import config
from diagnose_labels import run
from label_diagnosis import summarize

# 조건 type → 진단이 내놓아야 할 suspicion (여러 개면 그중 하나만 맞으면 정답)
EXPECTED_SUSPICION: dict[str, set[str]] = {
    "width": {"width"},
    "height": {"height"},
    "scale": {"scale"},
    "translation_x": {"translation_x"},
    "translation_y": {"translation_y"},
    "missing": {"missing"},
    "duplicate": {"duplicate"},
    # AABB 외접 근사 때문에 크기 계열과 구분 불가 (위 주의 참고)
    "rotation": {"width", "height", "scale"},
}
# clean은 "아무 유형도 두드러지지 않아야"(systematic=False) 정답이다.
# 총 의심 비율이 아니라 최대 유형 비율로 판정하는 이유는
# label_diagnosis.summarize()의 주석 참고.


def evaluate_condition(condition: config.Condition, limit: int | None) -> dict:
    root = config.CONDITIONS_DIR / condition.name
    findings, total_labels, _fit = run(root / "images" / "train",
                                       root / "labels" / "train", limit)
    summary = summarize(findings, total_labels)

    expected = EXPECTED_SUSPICION.get(condition.type)
    actual = summary["dominant_type"]

    if condition.type == "none":
        # 깨끗한 데이터셋은 어떤 유형도 계통적으로 몰리지 않아야 정답
        correct = not summary["systematic"]
        expected_label = "계통적 오류 없음"
    else:
        # 유형을 맞히는 것만으로는 부족하다 — 계통적이라고 판정까지 해야
        # 고객에게 "이 데이터셋은 재검수가 필요하다"고 말할 수 있다.
        correct = summary["systematic"] and actual in expected
        expected_label = "|".join(sorted(expected)) if len(expected) > 1 else next(iter(expected))

    return {
        "condition": condition.name,
        "type": condition.type,
        "magnitude": condition.magnitude,
        "expected": expected_label,
        "dominant_type": actual,
        "dominant_ratio": summary["dominant_ratio"],
        "systematic": summary["systematic"],
        "suspicion_ratio": summary["suspicion_ratio"],
        "total_labels": summary["total_labels"],
        "total_findings": summary["total_findings"],
        "correct": correct,
        "by_type": summary["by_type"],
    }


def main():
    parser = argparse.ArgumentParser(description="라벨 단위 진단 정확도 평가")
    parser.add_argument("--limit", type=int, default=80,
                        help="조건당 이미지 수 (기본 80 — 전체를 다 돌리면 오래 걸림)")
    parser.add_argument("--conditions", nargs="+", help="특정 조건만 평가")
    args = parser.parse_args()

    conditions = config.conditions_in_run_order()
    if args.conditions:
        by_name = {c.name: c for c in config.CONDITIONS}
        conditions = [by_name[n] for n in args.conditions]

    rows = []
    for i, condition in enumerate(conditions, 1):
        print(f"[{i}/{len(conditions)}] {condition.name} ...", flush=True)
        rows.append(evaluate_condition(condition, args.limit))

    n_correct = sum(1 for r in rows if r["correct"])
    accuracy = n_correct / len(rows) if rows else 0.0

    print(f"\n{'조건':<14} {'기대':<16} {'진단':<14} {'최대유형':>8} {'전체':>7}  판정")
    print("-" * 76)
    for r in rows:
        mark = "O" if r["correct"] else "X"
        note = " (회전=스케일 근사)" if r["type"] == "rotation" else ""
        print(f"{r['condition']:<14} {str(r['expected']):<16} {str(r['dominant_type']):<14} "
              f"{r['dominant_ratio'] * 100:>7.1f}% {r['suspicion_ratio'] * 100:>6.1f}%  {mark}{note}")

    print(f"\n진단 정확도: {n_correct}/{len(rows)} = {accuracy * 100:.1f}%")

    out_dir = config.EXPERIMENT_ROOT
    json_path = out_dir / "label_diagnosis_eval.json"
    json_path.write_text(
        json.dumps({"accuracy": round(accuracy, 4), "results": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "label_diagnosis_eval.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["condition", "type", "magnitude", "expected", "dominant_type",
              "dominant_ratio", "systematic", "suspicion_ratio",
              "total_labels", "total_findings", "correct"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"저장 → {json_path}\n저장 → {csv_path}")


if __name__ == "__main__":
    main()
