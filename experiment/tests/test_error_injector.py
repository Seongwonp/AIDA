"""error_injector.py의 좌표 변형 로직(순수 함수, GPU/학습 불필요) 단위 테스트."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from error_injector import (  # noqa: E402
    apply_height,
    apply_rotation,
    apply_width,
    pixel_to_yolo_line,
    yolo_to_pixel,
)

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
