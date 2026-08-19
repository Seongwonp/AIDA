"""실험 전역 설정. 모든 스크립트가 이 값들을 공유해야 조건 간 confounding이 생기지 않는다.

값은 .env 파일(없으면 OS 환경변수, 그마저 없으면 기본값)에서 읽는다.
전체 목록·기본값은 .env.example 참고.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_ROOT = Path(__file__).resolve().parent
RAW_DIR = EXPERIMENT_ROOT / "data" / "raw"
PROCESSED_DIR = EXPERIMENT_ROOT / "data" / "processed"
IMAGES_TRAIN_DIR = PROCESSED_DIR / "images" / "train"
IMAGES_VAL_DIR = PROCESSED_DIR / "images" / "val"
LABELS_GT_TRAIN_DIR = PROCESSED_DIR / "labels_gt" / "train"
LABELS_GT_VAL_DIR = PROCESSED_DIR / "labels_gt" / "val"
SEED = int(os.environ.get("AIDA_SEED", 42))
# 오류 주입 전용 시드. train/val 분할(SEED)은 고정하고 오류 주입 패턴만 바꿔
# 동일 데이터셋에서 반복 실험을 수행한다. 기본값은 SEED와 동일(기존 동작 유지).
ERROR_SEED = int(os.environ.get("AIDA_ERROR_SEED", SEED))

# ERROR_SEED가 기본값(SEED=42)이 아닐 때 별도 디렉토리를 사용해 기존 결과를 보존한다.
_esuffix = f"_e{ERROR_SEED}" if ERROR_SEED != 42 else ""

CONDITIONS_DIR = EXPERIMENT_ROOT / f"conditions{_esuffix}"
DATA_YAML_DIR = EXPERIMENT_ROOT / f"data_yaml{_esuffix}"
RUNS_DIR = EXPERIMENT_ROOT / f"runs{_esuffix}"
METRICS_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics.csv"

# 다중 seed 실험용 누적 CSV (모든 seed 결과 포함, error_seed 컬럼 추가)
MULTI_SEED_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics_multi_seed.csv"
OBB_MULTI_SEED_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics_obb_multi_seed.csv"
# 집계 CSV: aggregate_seeds.py가 mean/std를 계산해 여기 저장
AGG_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics_agg.csv"
OBB_AGG_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics_obb_agg.csv"
TARGET_CLASS = os.environ.get("AIDA_TARGET_CLASS", "Car")
CLASS_ID = 0  # YOLO 클래스 인덱스 (Car 단일 클래스이므로 항상 0)

# 스모크 테스트 시 AIDA_N_TRAIN=20 AIDA_N_VAL=10 AIDA_EPOCHS=1 처럼 .env나 환경변수로 오버라이드
N_TRAIN = int(os.environ.get("AIDA_N_TRAIN", 400))  # 300~500장 범위 중간값
N_VAL = int(os.environ.get("AIDA_N_VAL", 120))  # 100~150장 범위 중간값

ERROR_RATIO = float(os.environ.get("AIDA_ERROR_RATIO", 0.3))  # 라벨 중 오류를 주입할 비율

EPOCHS = int(os.environ.get("AIDA_EPOCHS", 50))
BATCH_SIZE = int(os.environ.get("AIDA_BATCH_SIZE", 16))
IMG_SIZE = int(os.environ.get("AIDA_IMG_SIZE", 640))
DEVICE = os.environ.get("AIDA_DEVICE", "auto")  # auto: resolve_device()가 cuda>mps>cpu 순 자동 감지

KITTI_LABEL_URL = os.environ.get(
    "AIDA_KITTI_LABEL_URL", "https://s3.eu-central-1.amazonaws.com/avg-kitti/data_object_label_2.zip"
)
KITTI_IMAGE_URL = os.environ.get(
    "AIDA_KITTI_IMAGE_URL", "https://s3.eu-central-1.amazonaws.com/avg-kitti/data_object_image_2.zip"
)


@dataclass(frozen=True)
class Condition:
    name: str
    type: str  # none | width | height | rotation | translation_x | translation_y | scale
    magnitude: float  # % (width/height/scale/translation) 또는 degree (rotation)


CONDITIONS: list[Condition] = [
    Condition("clean", "none", 0),
    Condition("width_m30", "width", -30),
    Condition("width_m15", "width", -15),
    Condition("width_p15", "width", 15),
    Condition("width_p30", "width", 30),
    Condition("height_m30", "height", -30),
    Condition("height_m15", "height", -15),
    Condition("height_p15", "height", 15),
    Condition("height_p30", "height", 30),
    Condition("rot_m15", "rotation", -15),
    Condition("rot_m7_5", "rotation", -7.5),
    Condition("rot_p7_5", "rotation", 7.5),
    Condition("rot_p15", "rotation", 15),
    # 확장 검증용 8개: 국방특허(10-2664201) 청구항에 명시된 오프셋은 가로·세로·회전각
    # 3가지뿐이다(docs/06-decisions.md "특허 청구항과 오류 유형 정합성 확인"). 중심점
    # 이동·스케일은 특허 청구항에 없는 보조 유형이라, 발표에서는 위 3유형(13개 조건)을
    # 주력으로 내세우고 이 8개는 "확장 검증"으로 톤을 구분해야 한다.
    Condition("trans_x_m15", "translation_x", -15),
    Condition("trans_x_p15", "translation_x", 15),
    Condition("trans_y_m15", "translation_y", -15),
    Condition("trans_y_p15", "translation_y", 15),
    Condition("scale_m15", "scale", -15),
    Condition("scale_p15", "scale", 15),
    Condition("scale_m30", "scale", -30),
    Condition("scale_p30", "scale", 30),
]

# 위 "확장 검증용 8개"(중심점 이동·스케일). run_all.py --priority all 실행 시
# 핵심 13개 다음 순서로 학습된다 (conditions_in_run_order 참고).
NEXT_PHASE_CONDITIONS: list[Condition] = CONDITIONS[13:]

# 시간 리스크 관리: 핵심 7개(clean, width±30, height±30, rot±15)를 먼저 실행하고
# 세분화 6개(width±15, height±15, rot±7.5)는 이어서 실행한다.
PRIORITY_1_NAMES = [
    "clean", "width_m30", "width_p30", "height_m30", "height_p30", "rot_m15", "rot_p15",
]
PRIORITY_2_NAMES = [
    "width_m15", "width_p15", "height_m15", "height_p15", "rot_m7_5", "rot_p7_5",
]

# ── OBB 실험 설정 ──────────────────────────────────────────────────────────────
# 기존 AABB 파이프라인과 완전히 독립된 경로를 사용한다.
# 이미지는 동일한 KITTI 이미지를 심볼릭 링크로 재사용하고,
# 라벨만 polygon OBB 포맷(class x1 y1 x2 y2 x3 y3 x4 y4)으로 달라진다.
OBB_LABELS_GT_TRAIN_DIR = PROCESSED_DIR / "labels_gt_obb" / "train"
OBB_LABELS_GT_VAL_DIR = PROCESSED_DIR / "labels_gt_obb" / "val"
OBB_CONDITIONS_DIR = EXPERIMENT_ROOT / f"conditions_obb{_esuffix}"
OBB_DATA_YAML_DIR = EXPERIMENT_ROOT / f"data_yaml_obb{_esuffix}"
OBB_RUNS_DIR = EXPERIMENT_ROOT / f"runs_obb{_esuffix}"
OBB_METRICS_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics_obb.csv"

# 회전 오류에 집중: AABB의 rot_m15 ≈ rot_p15(방향 소실) vs OBB의 rot_m15 ≠ rot_p15(방향 보존)
OBB_CONDITIONS: list[Condition] = [
    Condition("obb_clean", "none", 0),
    Condition("obb_rot_m15", "rotation", -15),
    Condition("obb_rot_m7_5", "rotation", -7.5),
    Condition("obb_rot_p7_5", "rotation", 7.5),
    Condition("obb_rot_p15", "rotation", 15),
]

_BY_NAME = {c.name: c for c in CONDITIONS}
_OBB_BY_NAME = {c.name: c for c in OBB_CONDITIONS}


def conditions_in_run_order() -> list[Condition]:
    ordered_names = PRIORITY_1_NAMES + PRIORITY_2_NAMES + [c.name for c in NEXT_PHASE_CONDITIONS]
    return [_BY_NAME[n] for n in ordered_names]


def resolve_device() -> str:
    """AIDA_DEVICE=auto(기본값)면 cuda > mps > cpu 순으로 이 머신에서 실제 쓸 수 있는
    디바이스를 자동 감지한다. cuda/mps/cpu를 명시하면 가용성 확인 없이 그대로 쓴다
    (다른 값을 강제하고 싶을 때 사용).

    이 방식으로 M1 Mac(mps)과 NVIDIA GPU가 있는 데스크탑(cuda) 양쪽에서 .env 수정
    없이 같은 코드가 최적 디바이스를 잡는다.
    """
    if DEVICE != "auto":
        return DEVICE
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"
