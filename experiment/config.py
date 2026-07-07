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
CONDITIONS_DIR = EXPERIMENT_ROOT / "conditions"
DATA_YAML_DIR = EXPERIMENT_ROOT / "data_yaml"
RUNS_DIR = EXPERIMENT_ROOT / "runs"
METRICS_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics.csv"

SEED = int(os.environ.get("AIDA_SEED", 42))
TARGET_CLASS = os.environ.get("AIDA_TARGET_CLASS", "Car")
CLASS_ID = 0  # YOLO 클래스 인덱스 (Car 단일 클래스이므로 항상 0)

# 스모크 테스트 시 AIDA_N_TRAIN=20 AIDA_N_VAL=10 AIDA_EPOCHS=1 처럼 .env나 환경변수로 오버라이드
N_TRAIN = int(os.environ.get("AIDA_N_TRAIN", 400))  # 300~500장 범위 중간값
N_VAL = int(os.environ.get("AIDA_N_VAL", 120))  # 100~150장 범위 중간값

ERROR_RATIO = float(os.environ.get("AIDA_ERROR_RATIO", 0.3))  # 라벨 중 오류를 주입할 비율

EPOCHS = int(os.environ.get("AIDA_EPOCHS", 50))
BATCH_SIZE = int(os.environ.get("AIDA_BATCH_SIZE", 16))
IMG_SIZE = int(os.environ.get("AIDA_IMG_SIZE", 640))
DEVICE = os.environ.get("AIDA_DEVICE", "mps")  # M1 Mac. 사용 불가 시 resolve_device()가 cpu로 폴백

KITTI_LABEL_URL = os.environ.get(
    "AIDA_KITTI_LABEL_URL", "https://s3.eu-central-1.amazonaws.com/avg-kitti/data_object_label_2.zip"
)
KITTI_IMAGE_URL = os.environ.get(
    "AIDA_KITTI_IMAGE_URL", "https://s3.eu-central-1.amazonaws.com/avg-kitti/data_object_image_2.zip"
)


@dataclass(frozen=True)
class Condition:
    name: str
    type: str  # none | width | height | rotation
    magnitude: float  # % (width/height) 또는 degree (rotation)


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
]

# 시간 리스크 관리: 핵심 7개(clean, width±30, height±30, rot±15)를 먼저 실행하고
# 세분화 6개(width±15, height±15, rot±7.5)는 이어서 실행한다.
PRIORITY_1_NAMES = [
    "clean", "width_m30", "width_p30", "height_m30", "height_p30", "rot_m15", "rot_p15",
]
PRIORITY_2_NAMES = [
    "width_m15", "width_p15", "height_m15", "height_p15", "rot_m7_5", "rot_p7_5",
]

_BY_NAME = {c.name: c for c in CONDITIONS}


def conditions_in_run_order() -> list[Condition]:
    ordered_names = PRIORITY_1_NAMES + PRIORITY_2_NAMES
    return [_BY_NAME[n] for n in ordered_names]


def resolve_device() -> str:
    """DEVICE가 mps인데 이 머신에서 못 쓰면 cpu로 자동 폴백."""
    if DEVICE == "mps":
        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"
    return DEVICE
