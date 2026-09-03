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
LABELS_GT_TRAIN_DIR: Path  # 아래 _csuffix 확정 후 대입

# 학습·진단에 쓸 KITTI 클래스. 쉼표로 여러 개를 주면 다중 클래스 실험이 된다
# (예: AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"). 순서가 곧 YOLO 클래스 인덱스다.
CLASS_NAMES = [c.strip() for c in os.environ.get("AIDA_CLASSES", "Car").split(",") if c.strip()]
CLASS_IDS = {name: i for i, name in enumerate(CLASS_NAMES)}
# 단일 클래스 시절 이름들 — 기존 스크립트 호환용
TARGET_CLASS = os.environ.get("AIDA_TARGET_CLASS", CLASS_NAMES[0])
CLASS_ID = 0
MULTICLASS = len(CLASS_NAMES) > 1

SEED = int(os.environ.get("AIDA_SEED", 42))
# 오류 주입 전용 시드. train/val 분할(SEED)은 고정하고 오류 주입 패턴만 바꿔
# 동일 데이터셋에서 반복 실험을 수행한다. 기본값은 SEED와 동일(기존 동작 유지).
ERROR_SEED = int(os.environ.get("AIDA_ERROR_SEED", SEED))

# ERROR_SEED가 기본값(SEED=42)이 아닐 때 별도 디렉토리를 사용해 기존 결과를 보존한다.
_esuffix = f"_e{ERROR_SEED}" if ERROR_SEED != 42 else ""
# 클래스 구성이 바뀌면 라벨·가중치·지표가 전부 달라진다. Car 단일 클래스로
# 쌓아온 결과(docs/21 A~K)를 덮어쓰지 않도록 경로를 통째로 분리한다.
# 프레임 선택 전략. 기본은 무작위 표집이고, cyclist_rich는 Cyclist가 많은
# 프레임을 골라 그 클래스의 인스턴스 수만 크게 늘린다 — 클래스 취약도가
# 희소성 때문인지 클래스 자체의 난이도 때문인지 가르는 실험용(docs/21 S).
# random       무작위 표집 (기본)
# cyclist_rich Cyclist가 많은 프레임 — 희소성 실험용(docs/21 S)
# all_local    로컬에 받아둔 전부 — 규모 실험용(docs/21 X)
# broad        cyclist_rich 평가셋을 제외한 1000장 — "넓고 강한 자" 실험용
#              (docs/21 Z의 빠진 사분면). 유출을 막으려고 평가 프레임을 뺐다.
FRAME_SELECT = os.environ.get("AIDA_FRAME_SELECT", "random")
SELECTED_FRAMES_FILE = (
    RAW_DIR / ("selected_frames.txt" if FRAME_SELECT == "random"
               else f"selected_frames_{FRAME_SELECT}.txt")
)

_DEFAULT_N_TRAIN = 400
N_TRAIN = int(os.environ.get("AIDA_N_TRAIN", _DEFAULT_N_TRAIN))  # 300~500장 범위 중간값
N_VAL = int(os.environ.get("AIDA_N_VAL", 120))  # 100~150장 범위 중간값

_csuffix = "" if CLASS_NAMES == ["Car"] else "_mc"
if FRAME_SELECT != "random":
    # 프레임 구성이 다르면 라벨도 가중치도 지표도 다른 실험이다
    _csuffix += f"_{FRAME_SELECT}"
if N_TRAIN != _DEFAULT_N_TRAIN:
    # 학습 규모가 다르면 모델도 지표도 달라진다. 접미사가 없으면 800장 실험이
    # 400장 결과를 덮는다 — check_consistency.py가 잡는 바로 그 유형이다.
    _csuffix += f"_n{N_TRAIN}"
_esuffix = _csuffix + _esuffix

LABELS_GT_TRAIN_DIR = PROCESSED_DIR / f"labels_gt{_csuffix}" / "train"
LABELS_GT_VAL_DIR = PROCESSED_DIR / f"labels_gt{_csuffix}" / "val"

CONDITIONS_DIR = EXPERIMENT_ROOT / f"conditions{_esuffix}"
DATA_YAML_DIR = EXPERIMENT_ROOT / f"data_yaml{_esuffix}"
RUNS_DIR = EXPERIMENT_ROOT / f"runs{_esuffix}"
METRICS_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / f"metrics{_csuffix}.csv"

# 다중 seed 실험용 누적 CSV (모든 seed 결과 포함, error_seed 컬럼 추가)
# 클래스 구성이 다르면 다른 실험이다. 접미사가 없으면 다중 클래스로 3-seed를
# 돌렸을 때 조건 이름이 같아서(width_m30 등) Car의 3-seed 결과를 덮어쓴다 —
# (error_seed, condition)으로 병합하기 때문에 조용히 사라진다.
MULTI_SEED_CSV = (EXPERIMENT_ROOT.parent / "backend" / "app" / "data"
                  / f"metrics{_csuffix}_multi_seed.csv")
OBB_MULTI_SEED_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics_obb_multi_seed.csv"
# 집계 CSV: aggregate_seeds.py가 mean/std를 계산해 여기 저장
AGG_CSV = (EXPERIMENT_ROOT.parent / "backend" / "app" / "data"
           / f"metrics{_csuffix}_agg.csv")
OBB_AGG_CSV = EXPERIMENT_ROOT.parent / "backend" / "app" / "data" / "metrics_obb_agg.csv"

# 스모크 테스트 시 AIDA_N_TRAIN=20 AIDA_N_VAL=10 AIDA_EPOCHS=1 처럼 .env나 환경변수로 오버라이드

ERROR_RATIO = float(os.environ.get("AIDA_ERROR_RATIO", 0.3))  # 라벨 중 오류를 주입할 비율

# 유형 신뢰도 보정 프로파일(JSON) 경로. 지정하면 label_diagnosis의 기본 상수
# 위에 덮어쓴다. 기본 상수는 KITTI Car 단일 클래스 실측값이고, 도메인이
# 바뀌면 evaluate_box_accuracy.py --write-profile 로 새로 재서 지정하면 된다.
RELIABILITY_PROFILE = os.environ.get("AIDA_RELIABILITY_PROFILE", "")

EPOCHS = int(os.environ.get("AIDA_EPOCHS", 50))
BATCH_SIZE = int(os.environ.get("AIDA_BATCH_SIZE", 16))
# 데이터로더 워커 수. ultralytics 기본값 8을 그대로 쓰면 워커마다 torch를 얹어
# 약 840MB씩 잡아, 커밋 여유가 없는 상태에서 WinError 1455(페이징 부족)로
# 학습이 죽는다. 결과에는 영향이 없음을 실측으로 확인했다(docs/21 S).
WORKERS = int(os.environ.get("AIDA_WORKERS", 8))
# 학습 시드. SEED와 분리해 둔 이유는, SEED를 바꾸면 train/val 분할까지 바뀌어
# 아예 다른 데이터셋이 되기 때문이다. 같은 데이터셋을 여러 번 학습해 실행 간
# 산포를 재려면 분할은 고정하고 학습 시드만 움직여야 한다(docs/21 T).
TRAIN_SEED = int(os.environ.get("AIDA_TRAIN_SEED", SEED))
# 반복 학습이 서로를 덮어쓰지 않게 실행 폴더·지표 행 이름에 붙이는 꼬리표.
RUN_SUFFIX = os.environ.get("AIDA_RUN_SUFFIX", "")
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
    type: str  # none | width | height | rotation | translation_x | translation_y | scale | missing | duplicate
    magnitude: float  # % (width/height/scale/translation) 또는 degree (rotation)
    # missing/duplicate에서는 magnitude가 "라벨의 몇 %가 이 오류를 겪는가" 자체다
    # (다른 타입처럼 ERROR_RATIO 30% 중 얼마나 세게 변형하는지가 아니라, 영향받는
    # 라벨의 비율 자체를 의미 — error_injector.build_condition_labels 참고)


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
    # 라벨링 실무에서 흔한 두 가지 오류(기하학적 왜곡이 아니라 "박스 존재 자체"의
    # 오류): missing(라벨 누락), duplicate(같은 객체에 라벨 중복). docs/21 B 항목.
    Condition("missing_10", "missing", 10),
    Condition("missing_20", "missing", 20),
    Condition("missing_30", "missing", 30),
    Condition("duplicate_10", "duplicate", 10),
    Condition("duplicate_20", "duplicate", 20),
    Condition("duplicate_30", "duplicate", 30),
]

# 위 "확장 검증용 8개"(중심점 이동·스케일). run_all.py --priority all 실행 시
# 핵심 13개 다음 순서로 학습된다 (conditions_in_run_order 참고).
NEXT_PHASE_CONDITIONS: list[Condition] = CONDITIONS[13:21]

# missing/duplicate 6개. NEXT_PHASE_CONDITIONS와 마찬가지로
# conditions_in_run_order()가 유일한 조건 출처가 되도록 여기 등록한다 —
# run_all.py가 하드코딩된 이름 리스트를 다시 쓰다가 조건을 빠뜨리는 사고가
# 있었으므로(docs/21 "다중 seed 검증 결과" 참고) 절대 반복하지 말 것.
NEW_ERROR_TYPE_CONDITIONS: list[Condition] = CONDITIONS[21:]

# 시간 리스크 관리: 핵심 7개(clean, width±30, height±30, rot±15)를 먼저 실행하고
# 세분화 6개(width±15, height±15, rot±7.5)는 이어서 실행한다.
PRIORITY_1_NAMES = [
    "clean", "width_m30", "width_p30", "height_m30", "height_p30", "rot_m15", "rot_p15",
]
PRIORITY_2_NAMES = [
    "width_m15", "width_p15", "height_m15", "height_p15", "rot_m7_5", "rot_p7_5",
]

# ── 혼합 오류 조건 (docs/21 F 재보정용) ────────────────────────────────────────
# 기존 26개 조건은 각각 오류 유형이 하나뿐이라, 진단 신뢰도를 "대표 유형일
# 때 / 아닐 때"로 갈라 재면 후자가 사실상 "그 유형이 아예 없을 때"의 값이
# 된다. 실제로 두 유형이 섞인 데이터셋에서 2차 유형이 얼마나 미더운지는
# 그 조건들로는 알 수 없어서, 여기서 섞인 조건을 따로 만든다.
#
# **학습하지 않는다.** 라벨 단위 진단은 clean 모델로 추론만 하고 라벨과
# 대조하므로(diagnose_labels.run 참고) 라벨만 있으면 된다. 그래서 이 목록은
# conditions_in_run_order()에 일부러 넣지 않는다 — 넣으면 run_all.py가
# 학습까지 돌려 몇 시간을 낭비한다.


@dataclass(frozen=True)
class MixedCondition:
    """두 오류 유형이 섞인 조건. 라벨 하나에는 최대 한 유형만 주입한다
    (라벨러가 박스마다 다른 실수를 하는 상황에 대응).

    rate가 주입 비율이고, magnitude는 기하학적 변형 강도다. missing/duplicate는
    변형 강도라는 게 없어서 magnitude를 쓰지 않는다(rate가 곧 강도).
    """
    name: str
    primary_type: str
    primary_magnitude: float
    primary_rate: float
    secondary_type: str
    secondary_magnitude: float
    secondary_rate: float


# primary 30% / secondary 15%로 고정해 대표 유형이 뚜렷하게 갈리도록 했다.
# 7개 유형이 각각 한 번씩 secondary로 등장한다.
MIXED_CONDITIONS: list[MixedCondition] = [
    MixedCondition("mix_scale_missing", "scale", -30, 0.30, "missing", 0, 0.15),
    MixedCondition("mix_missing_scale", "missing", 0, 0.30, "scale", -30, 0.15),
    MixedCondition("mix_width_height", "width", -30, 0.30, "height", 30, 0.15),
    MixedCondition("mix_height_width", "height", 30, 0.30, "width", -30, 0.15),
    MixedCondition("mix_scale_transx", "scale", -30, 0.30, "translation_x", 15, 0.15),
    MixedCondition("mix_missing_duplicate", "missing", 0, 0.30, "duplicate", 0, 0.15),
    MixedCondition("mix_duplicate_transy", "duplicate", 0, 0.30, "translation_y", 15, 0.15),
]
MIXED_CONDITIONS_DIR = EXPERIMENT_ROOT / f"conditions_mixed{_esuffix}"

# 클래스 오기입 조건 — 다중 클래스에서만 의미가 있어서 CONDITIONS와 분리했다.
# 단일 클래스 실행에는 아예 안 들어간다(바꿀 다른 클래스가 없다).
# 자기 정제 실험이 만든 부분집합 조건들(docs/21 W). refine_ruler.py가 폴더를
# 만들면 여기서 이름으로 찾아 학습할 수 있게 등록한다.
REFINED_CONDITIONS: list[Condition] = [
    Condition(f"{c}_refined{pct}", "refined", pct)
    for c in ("scale_m30", "missing_30", "width_m30")
    for pct in (30, 50, 70)
] + [
    # 데이터 크기와 라벨 품질을 분리하는 대조군: refined50과 같은 200장에
    # 깨끗한 라벨을 붙인 것. 손해가 크기 탓인지 오류 탓인지 가른다.
    Condition("clean_sub200", "refined", 0),
    Condition("clean_sub400", "refined", 0),
]

# 재검수 시뮬레이션이 만든 조건들(docs/21 T). simulate_review.py가 폴더를
# 만들면 여기서 이름으로 찾아 학습할 수 있게 등록한다.
REVIEW_SIM_CONDITIONS: list[Condition] = [
    Condition(f"scale_m30_fix_{order}_{pct}", "review_sim", pct)
    for order in ("severity", "class_weighted", "random")
    for pct in (25, 50)
] + [
    # 같은 워커 설정으로 학습한 기준선(고치지 않음)과 상한(오류 없음)
    Condition("scale_m30_asis", "review_sim", 0),
    Condition("clean_asis", "review_sim", 0),
]

CLASS_SWAP_CONDITIONS: list[Condition] = [
    Condition("class_swap_10", "class_swap", 10),
    Condition("class_swap_20", "class_swap", 20),
    Condition("class_swap_30", "class_swap", 30),
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

_BY_NAME = {c.name: c for c in
             CONDITIONS + CLASS_SWAP_CONDITIONS + REVIEW_SIM_CONDITIONS
             + REFINED_CONDITIONS}
_OBB_BY_NAME = {c.name: c for c in OBB_CONDITIONS}


def conditions_in_run_order() -> list[Condition]:
    if MULTICLASS:
        # 다중 클래스에서는 클래스 오기입 조건이 추가된다
        return ([_BY_NAME[n] for n in _single_class_order()] + CLASS_SWAP_CONDITIONS)
    return [_BY_NAME[n] for n in _single_class_order()]


def _single_class_order() -> list[str]:
    ordered_names = (
        PRIORITY_1_NAMES
        + PRIORITY_2_NAMES
        + [c.name for c in NEXT_PHASE_CONDITIONS]
        + [c.name for c in NEW_ERROR_TYPE_CONDITIONS]
    )
    return ordered_names


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
