"""error_injector.py의 좌표 변형 로직(순수 함수, GPU/학습 불필요) 단위 테스트."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from error_injector import (  # noqa: E402
    apply_height,
    apply_rotation,
    apply_scale,
    apply_translation_x,
    apply_translation_y,
    apply_width,
    pixel_to_yolo_line,
    transform_box,
    yolo_to_pixel,
)
from config import Condition  # noqa: E402

BOX = (0.0, 0.0, 100.0, 50.0)  # left, top, right, bottom (width=100, height=50)


def test_apply_width_shrinks_around_center():
    left, top, right, bottom = apply_width(BOX, -30)
    assert (left, right) == pytest.approx((15.0, 85.0))
    assert (top, bottom) == pytest.approx((0.0, 50.0))  # 세로는 불변


def test_apply_width_grows_around_center():
    left, top, right, bottom = apply_width(BOX, 30)
    assert (left, right) == pytest.approx((-15.0, 115.0))


def test_apply_height_shrinks_around_center():
    left, top, right, bottom = apply_height(BOX, -30)
    assert (top, bottom) == pytest.approx((7.5, 42.5))
    assert (left, right) == pytest.approx((0.0, 100.0))  # 가로는 불변


def test_apply_translation_x_moves_center_without_resizing():
    left, top, right, bottom = apply_translation_x(BOX, 15)
    assert (left, right) == pytest.approx((15.0, 115.0))
    assert (top, bottom) == pytest.approx((0.0, 50.0))
    assert (right - left, bottom - top) == pytest.approx((100.0, 50.0))


def test_apply_translation_y_moves_center_without_resizing():
    left, top, right, bottom = apply_translation_y(BOX, -20)
    assert (left, right) == pytest.approx((0.0, 100.0))
    assert (top, bottom) == pytest.approx((-10.0, 40.0))
    assert (right - left, bottom - top) == pytest.approx((100.0, 50.0))


def test_apply_scale_resizes_both_axes_around_center():
    left, top, right, bottom = apply_scale(BOX, 20)
    assert (left, top, right, bottom) == pytest.approx((-10.0, -5.0, 110.0, 55.0))


def test_transform_box_supports_next_phase_conditions():
    condition = Condition("scale_p20", "scale", 20)
    assert transform_box(BOX, condition) == pytest.approx((-10.0, -5.0, 110.0, 55.0))


def test_apply_rotation_zero_degrees_is_identity():
    result = apply_rotation(BOX, 0)
    assert result == pytest.approx(BOX)


def test_apply_rotation_90_degrees_swaps_width_and_height():
    """90도 회전은 축정렬 재계산 후 가로·세로가 정확히 뒤바뀐다 (중심점은 불변)."""
    left, top, right, bottom = apply_rotation(BOX, 90)
    assert (right - left) == pytest.approx(50.0)  # 원래 세로(50)가 새 가로가 됨
    assert (bottom - top) == pytest.approx(100.0)  # 원래 가로(100)가 새 세로가 됨
    assert ((left + right) / 2, (top + bottom) / 2) == pytest.approx((50.0, 25.0))


def test_apply_rotation_nonzero_angle_enlarges_non_square_box():
    """알려진 한계: 축정렬 박스는 90도의 배수가 아닌 각도로 회전하면 항상 더 커진다
    (docs/11-professor-feedback.md 2번 항목 — 회전 방향과 무관하게 박스가 커지는
    형태로 나타나는 현상을 코드 수준에서 문서화하는 회귀 테스트).
    """
    original_area = (BOX[2] - BOX[0]) * (BOX[3] - BOX[1])

    left, top, right, bottom = apply_rotation(BOX, 15)
    rotated_area = (right - left) * (bottom - top)
    assert rotated_area > original_area

    # 반대 방향(-15도)도 마찬가지로 커진다 — 방향에 따른 비대칭이 없다는 뜻
    left2, top2, right2, bottom2 = apply_rotation(BOX, -15)
    rotated_area_neg = (right2 - left2) * (bottom2 - top2)
    assert rotated_area_neg > original_area
    assert rotated_area == pytest.approx(rotated_area_neg, rel=1e-9)


def test_yolo_pixel_roundtrip():
    img_w, img_h = 640, 480
    line = "0 0.500000 0.500000 0.200000 0.100000"
    box = yolo_to_pixel(line, img_w, img_h)
    roundtrip = pixel_to_yolo_line(box, img_w, img_h)
    assert roundtrip == line


def test_pixel_to_yolo_line_clamps_out_of_bounds():
    img_w, img_h = 100, 100
    # 이미지 경계를 벗어나는 박스 (오류 주입으로 인해 발생 가능한 상황)
    line = pixel_to_yolo_line((-50, -50, 150, 150), img_w, img_h)
    _, cx, cy, w, h = line.split()
    assert 0.0 <= float(cx) <= 1.0
    assert 0.0 <= float(cy) <= 1.0
    assert 0.0 <= float(w) <= 1.0
    assert 0.0 <= float(h) <= 1.0


# ── 오류 주입 기록 (박스 단위 진단 정확도의 정답지) ──────────────────────────
# evaluate_box_accuracy.py가 이 기록을 정답으로 삼아 채점하므로, 기록이 틀리면
# 정확도 숫자 자체가 무의미해진다. magnitude=100으로 두어 RNG와 무관하게
# "모든 박스가 오류"인 결정적 상황을 만들어 인덱스 규칙만 검증한다.

def _make_dataset(tmp_path, n_boxes: int):
    from PIL import Image

    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels_gt"
    image_dir.mkdir()
    label_dir.mkdir()
    Image.new("RGB", (100, 100)).save(image_dir / "frame.png")
    lines = [f"0 0.{i + 1}00000 0.500000 0.100000 0.100000" for i in range(n_boxes)]
    (label_dir / "frame.txt").write_text("\n".join(lines) + "\n")
    return image_dir, label_dir


def test_record_marks_every_transformed_box(tmp_path):
    from error_injector import build_condition_labels

    image_dir, label_dir = _make_dataset(tmp_path, 3)
    out_dir = tmp_path / "out"
    # ERROR_RATIO는 환경값이라 건드리지 않고, 기록 구조만 확인한다
    record = build_condition_labels(
        Condition("t", "width", -30), image_dir, label_dir, out_dir
    )
    errored = record.get("frame", {}).get("errored", [])
    # 출력 줄 수는 그대로 3줄이고, 기록된 인덱스는 그 범위 안이어야 한다
    out_lines = [l for l in (out_dir / "frame.txt").read_text().splitlines() if l.strip()]
    assert len(out_lines) == 3
    assert all(0 <= i < 3 for i in errored)


def test_missing_record_uses_coordinates_not_indices(tmp_path):
    """누락은 출력에 가리킬 줄이 없으므로 좌표로 기록해야 한다."""
    from error_injector import build_condition_labels

    image_dir, label_dir = _make_dataset(tmp_path, 3)
    out_dir = tmp_path / "out"
    record = build_condition_labels(
        Condition("t", "missing", 100), image_dir, label_dir, out_dir
    )
    entry = record["frame"]
    assert entry["errored"] == []  # 남은 줄이 없으니 인덱스 기록도 없음
    assert len(entry["dropped"]) == 3  # 세 박스 모두 좌표로 기록
    assert all(len(box) == 4 for box in entry["dropped"])
    out_lines = [l for l in (out_dir / "frame.txt").read_text().splitlines() if l.strip()]
    assert out_lines == []


def test_duplicate_record_points_at_inserted_line(tmp_path):
    """복제본은 원본 바로 뒤에 끼워지므로 기록은 홀수 인덱스여야 한다."""
    from error_injector import build_condition_labels

    image_dir, label_dir = _make_dataset(tmp_path, 3)
    out_dir = tmp_path / "out"
    record = build_condition_labels(
        Condition("t", "duplicate", 100), image_dir, label_dir, out_dir
    )
    out_lines = [l for l in (out_dir / "frame.txt").read_text().splitlines() if l.strip()]
    assert len(out_lines) == 6  # 원본 3 + 복제 3
    assert record["frame"]["errored"] == [1, 3, 5]


def test_clean_condition_records_nothing(tmp_path):
    from error_injector import build_condition_labels

    image_dir, label_dir = _make_dataset(tmp_path, 3)
    record = build_condition_labels(
        Condition("clean", "none", 0), image_dir, label_dir, tmp_path / "out"
    )
    assert record == {}
