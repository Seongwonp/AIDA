"""고객이 업로드한 데이터셋을 clean 기준 모델로 진단한다 (docs/21 C).

학습을 새로 하지 않는다 — 이미 clean 조건으로 학습된 모델을 업로드
데이터셋에 inference만 돌려 성능 벡터(precision·recall)를 뽑고, 그 벡터를
metrics.csv의 조건별 (precision, recall)과 비교해 가장 가까운 오류 유형을
후보로 제시한다.

한계 (알아야 할 것):
- 업로드 데이터셋 자체의 "정답 없는 상태에서의 절대 난이도"를 모르기 때문에,
  KITTI Car 기준으로 학습된 conditions의 (precision, recall) 값과 직접
  비교한다 — 업로드 데이터셋이 KITTI Car와 비슷한 난이도라고 가정하는
  것이다. 도메인이 많이 다르면(예: 실내 소형 물체) 진단이 부정확해진다.
  확정 진단이 아니라 재검수 우선순위를 좁히는 확률적 후보로만 쓸 것 —
  이 한계는 AIDA 전체의 포지셔닝(docs/16, docs/10 리스크대응)과 같은 결이다.

업로드 데이터셋 형식(YOLO, 단일 클래스):
  <dataset_dir>/images/*.{jpg,png}
  <dataset_dir>/labels/*.txt  (class cx cy w h, 정규화 좌표, class는 항상 0)

사용법:
  python diagnose_upload.py <dataset_id>
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from ultralytics import YOLO

import config

UPLOADS_DIR = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "uploads"
CLEAN_WEIGHTS = config.RUNS_DIR / "clean" / "weights" / "best.pt"


def build_data_yaml(dataset_dir: Path) -> Path:
    """train/val을 굳이 나누지 않는다 — 학습은 안 하고 model.val()만 돌리므로
    val 스플릿 하나만 있으면 된다. train 키는 ultralytics data.yaml 스펙상
    필요해서 같은 경로를 채워 넣는다(실제로 쓰이지 않음)."""
    data = {
        "path": str(dataset_dir.resolve()),
        "train": "images",
        "val": "images",
        "names": {config.CLASS_ID: config.TARGET_CLASS},
    }
    yaml_path = dataset_dir / "data.yaml"
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return yaml_path


def run_inference(dataset_dir: Path) -> dict:
    if not CLEAN_WEIGHTS.exists():
        raise RuntimeError(
            f"{CLEAN_WEIGHTS} 없음 — clean 조건이 먼저 학습돼 있어야 한다 "
            "(run_all.py로 최소 clean 조건은 학습된 상태여야 함)"
        )
    yaml_path = build_data_yaml(dataset_dir)
    model = YOLO(str(CLEAN_WEIGHTS))
    metrics = model.val(
        data=str(yaml_path),
        imgsz=config.IMG_SIZE,
        device=config.resolve_device(),
        split="val",
        verbose=False,
        project=str(dataset_dir),
        name="diagnosis_val",
        exist_ok=True,
    )
    box = metrics.box
    return {
        "map50": round(float(box.map50), 3),
        "map50_95": round(float(box.map), 3),
        "precision": round(float(box.mp), 3),
        "recall": round(float(box.mr), 3),
    }


def match_error_types(vector: dict, top_n: int = 5) -> list[dict]:
    """metrics.csv의 조건별 (precision, recall)과 유클리드 거리로 가장 가까운
    오류 유형 후보를 찾는다. 유형(type)별로 가장 가까운 조건 하나만 대표로 뽑아
    (기존 /api/diagnose와 동일한 groupby 관례) 거리 오름차순으로 정렬한다.
    """
    df = pd.read_csv(config.METRICS_CSV)
    df = df[df["condition"] != "clean"].copy()
    df["distance"] = (
        (df["precision"] - vector["precision"]) ** 2
        + (df["recall"] - vector["recall"]) ** 2
    ) ** 0.5

    candidates = []
    for error_type, group in df.groupby("type"):
        best = group.loc[group["distance"].idxmin()]
        candidates.append({
            "error_type": error_type,
            "closest_condition": best["condition"],
            "closest_magnitude": float(best["magnitude"]),
            "distance": round(float(best["distance"]), 4),
        })
    candidates.sort(key=lambda c: c["distance"])
    return candidates[:top_n]


def main():
    parser = argparse.ArgumentParser(description="업로드 데이터셋 오류 유형 진단")
    parser.add_argument("dataset_id")
    args = parser.parse_args()

    dataset_dir = UPLOADS_DIR / args.dataset_id
    if not dataset_dir.exists():
        raise RuntimeError(f"{dataset_dir} 없음")

    vector = run_inference(dataset_dir)
    candidates = match_error_types(vector)
    # 정밀도×재현율 기반 대략적인 점수 — mAP는 도메인 난이도에 따라 절대값이
    # 크게 흔들리므로(위 "한계" 참고) precision/recall 조합을 대신 쓴다.
    quality_score = round(vector["precision"] * vector["recall"] * 100)

    result = {
        "dataset_id": args.dataset_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "performance_vector": vector,
        "quality_score": quality_score,
        "candidates": candidates,
        "caveat": (
            "이 진단은 업로드하신 데이터셋이 KITTI Car와 비슷한 난이도라고 "
            "가정한 추정치입니다. 확정 진단이 아니라 재검수 우선순위를 좁히는 "
            "확률적 후보로 활용하세요."
        ),
    }
    out_path = dataset_dir / "diagnosis.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
