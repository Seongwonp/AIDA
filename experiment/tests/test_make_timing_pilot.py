"""파일럿 무대 만들기 (make_timing_pilot.py).

**정답을 본 이미지는 다시 쓰지 않는다.** 한 번 본 이미지는 두 번째에 빨라지고,
그 시간은 판정 시간이 아니라 기억이다. timing1에서 정답표를 열었으므로 그
이미지들은 이후 시간 파일럿에서 빠져야 한다.
"""
import json

import pytest

import make_timing_pilot as mk

PNG_HEADER = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 4 + b"IHDR"
              + (100).to_bytes(4, "big") + (80).to_bytes(4, "big"))


def make_image(path, name):
    (path / name).write_bytes(PNG_HEADER + b"\x00" * 32)


def make_label(path, stem, rows=3):
    lines = [f"0 {0.2 + i * 0.2:.4f} 0.5 0.3 0.4" for i in range(rows)]
    (path / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def dataset(tmp_path):
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    for i in range(12):
        make_image(images, f"{i:06d}.png")
        make_label(labels, f"{i:06d}")
    return images, labels


def test_이미_쓴_이미지를_뺀다(dataset):
    images, labels = dataset
    exclude = {"000000.png", "000001.png", "000002.png"}
    chosen = mk.pick_images(images, labels, 9, seed=1, exclude=exclude)
    assert {p[0].name for p in chosen} & exclude == set()


def test_제외하지_않으면_전부_후보다(dataset):
    images, labels = dataset
    assert len(mk.pick_images(images, labels, 12, seed=1)) == 12


def test_두_집합이_겹치면_만들지_않는다(dataset, tmp_path, monkeypatch):
    """거르는 쪽이 고장 나면 기억으로 빨라진 시간을 판정 시간으로 센다."""
    images, labels = dataset

    # **거르는 쪽이 고장 난 상황을 만든다.** 제외 목록을 무시하고 그 이미지를
    # 그대로 돌려주는 `pick_images`를 끼운다.
    def ignores_exclude(images_dir, labels_dir, count, seed, exclude=None):
        return [(images / "000000.png", labels / "000000.txt", 100, 80)
                for _ in range(count)]

    monkeypatch.setattr(mk, "pick_images", ignores_exclude)

    with pytest.raises(SystemExit, match="제외해야 할 이미지"):
        mk.build(images, labels, tmp_path / "out", 3, seed=1,
                 class_names=["Car"], exclude={"000000.png"})


def test_라벨이_하나뿐인_이미지는_안_쓴다(tmp_path):
    """문맥이 있어야 판정할 수 있다 — 주변 라벨이 없으면 비교할 것이 없다."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    make_image(images, "a.png")
    make_label(labels, "a", rows=1)
    make_image(images, "b.png")
    make_label(labels, "b", rows=3)

    chosen = mk.pick_images(images, labels, 2, seed=1)
    assert [p[0].name for p in chosen] == ["b.png"]


def test_쓴_이미지_목록을_진단_결과에서_읽는다(tmp_path, monkeypatch):
    root = tmp_path / "uploads" / "abc"
    root.mkdir(parents=True)
    (root / "label_diagnosis.json").write_text(json.dumps({
        "review_queue": [{"image": "x.png"}, {"image": "y.png"},
                         {"image": "x.png"}],
    }), encoding="utf-8")
    monkeypatch.setattr(mk.config, "uploads_dir", lambda: tmp_path / "uploads")

    assert mk.used_images("abc") == {"x.png", "y.png"}


def test_없는_파일럿의_목록은_빈_집합이다(tmp_path, monkeypatch):
    monkeypatch.setattr(mk.config, "uploads_dir", lambda: tmp_path)
    assert mk.used_images("없는것") == set()


def test_후보에_틀린_것과_멀쩡한_것이_섞인다(dataset, tmp_path):
    """전부 진짜 오류면 판정이 아니라 확인 작업이 된다."""
    images, labels = dataset
    queue, answers = mk.build(images, labels, tmp_path / "out", 10, seed=3,
                              class_names=["Car"])
    kinds = {a["kind"] for a in answers}
    assert "wrong" in kinds and "clean" in kinds
    assert len(queue) == 10


def test_정답표는_진단_결과에_안_들어간다(dataset, tmp_path):
    """가림 판정 화면은 진단 결과만 읽는다. 열쇠가 새면 안 된다."""
    images, labels = dataset
    queue, _ = mk.build(images, labels, tmp_path / "out", 10, seed=3,
                        class_names=["Car"])
    text = json.dumps(queue, ensure_ascii=False)
    assert "truth" not in text and "kind" not in text
