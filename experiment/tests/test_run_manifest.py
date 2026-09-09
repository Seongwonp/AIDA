"""실행 명세가 재현에 필요한 것을 실제로 담는가 (docs/25 2단계).

**시드만으로 분할 보존을 대신하지 않는다**가 이 절의 요구다. 시드는 같은
프레임 풀을 전제하는데 그 풀은 저장소에 없다.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_manifest as M  # noqa: E402


def test_list_digest_ignores_order():
    """목록 해시는 순서에 안 흔들려야 한다 — 같은 분할이면 같은 값이다."""
    assert M.digest_of_list(["b", "a"]) == M.digest_of_list(["a", "b"])


def test_list_digest_changes_with_content():
    assert M.digest_of_list(["a", "b"]) != M.digest_of_list(["a", "c"])


def test_file_hash_reads_content(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    assert M.sha256_of(a) == M.sha256_of(b)
    b.write_bytes(b"other")
    assert M.sha256_of(a) != M.sha256_of(b)


def test_missing_file_is_none_not_crash(tmp_path):
    assert M.sha256_of(tmp_path / "없음.bin") is None


def test_dependency_versions_records_absence():
    """이 환경에 없는 것은 **없다고 적는다** — 추측해 채우지 않는다."""
    deps = M.dependency_versions()
    assert "python" in deps and deps["python"]
    for name in ("torch", "ultralytics"):
        assert name in deps          # 값은 None일 수 있다


def test_git_state_reports_cleanliness():
    """커밋만 적으면 재현할 때 없는 상태를 재현하려 하게 된다."""
    state = M.git_state()
    assert {"commit", "clean", "reproducible"} <= set(state)


def test_weights_record_marks_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(M.config, "EXPERIMENT_ROOT", tmp_path)
    rec = M.weights_record(["runs_없음/clean"])
    assert rec[0]["exists"] is False
    assert "sha256" not in rec[0]


def test_weights_record_hashes_and_reads_args(tmp_path, monkeypatch):
    monkeypatch.setattr(M.config, "EXPERIMENT_ROOT", tmp_path)
    run = tmp_path / "runs_x" / "clean"
    (run / "weights").mkdir(parents=True)
    (run / "weights" / "best.pt").write_bytes(b"weights")
    (run / "args.yaml").write_text("epochs: 50\nbatch: 16\nseed: 42\n", encoding="utf-8")

    rec = M.weights_record(["runs_x/clean"])[0]
    assert rec["exists"] is True
    assert len(rec["sha256"]) == 64
    assert rec["train_args"]["epochs"] == 50
    assert rec["train_args"]["seed"] == 42


def test_split_says_so_when_the_pool_is_missing(tmp_path, monkeypatch):
    """풀 파일이 없으면 **분할을 되살릴 수 없다**고 말해야 한다.

    조용히 빈 목록을 남기면 명세를 믿고 재현하려다 다른 분할을 얻는다.
    """
    monkeypatch.setattr(M.config, "SELECTED_FRAMES_FILE", tmp_path / "없음.txt")
    rec = M.split_record(hash_images=False)
    assert "error" in rec


def test_split_records_the_actual_ids(tmp_path, monkeypatch):
    pool = tmp_path / "pool.txt"
    pool.write_text("\n".join(f"{i:06d}" for i in range(30)), encoding="utf-8")
    monkeypatch.setattr(M.config, "SELECTED_FRAMES_FILE", pool)
    monkeypatch.setattr(M.config, "N_TRAIN", 20)
    monkeypatch.setattr(M.config, "N_VAL", 5)

    rec = M.split_record(hash_images=False)
    assert rec["pool_size"] == 30
    assert len(rec["train"]) == 20 and len(rec["val"]) == 5
    # 목록 자체가 남아야 한다 — 시드만으로 대신하지 않는다.
    assert rec["train_digest"] and rec["val_digest"]
    assert set(rec["train"]).isdisjoint(rec["val"]), "학습과 평가가 겹치면 안 된다"


def test_manifest_is_json_serialisable(tmp_path, monkeypatch):
    pool = tmp_path / "pool.txt"
    pool.write_text("\n".join(f"{i:06d}" for i in range(30)), encoding="utf-8")
    monkeypatch.setattr(M.config, "SELECTED_FRAMES_FILE", pool)
    monkeypatch.setattr(M.config, "N_TRAIN", 20)
    monkeypatch.setattr(M.config, "N_VAL", 5)
    monkeypatch.setattr(M.config, "EXPERIMENT_ROOT", tmp_path)

    text = json.dumps(M.build([], hash_images=False), ensure_ascii=False)
    assert "settings" in text and "seeds" in text


# --- 명세가 불완전한 것을 숨기지 않는가 (docs/25 2단계 보완) -------------------

def _fake_split(tmp_path, monkeypatch, train_names, val_names, make_train, make_val):
    """학습·평가 이미지 폴더를 따로 만든 fixture."""
    pool = tmp_path / "pool.txt"
    pool.write_text("\n".join(train_names + val_names), encoding="utf-8")
    tr, va = tmp_path / "images" / "train", tmp_path / "images" / "val"
    tr.mkdir(parents=True); va.mkdir(parents=True)
    for n in make_train:
        (tr / f"{n}.png").write_bytes(f"train-{n}".encode())
    for n in make_val:
        (va / f"{n}.png").write_bytes(f"val-{n}".encode())
    monkeypatch.setattr(M.config, "SELECTED_FRAMES_FILE", pool)
    monkeypatch.setattr(M.config, "IMAGES_TRAIN_DIR", tr)
    monkeypatch.setattr(M.config, "IMAGES_VAL_DIR", va)
    monkeypatch.setattr(M.config, "N_TRAIN", len(train_names))
    monkeypatch.setattr(M.config, "N_VAL", len(val_names))


def test_val_images_are_hashed_from_the_val_directory(tmp_path, monkeypatch):
    """평가 이미지를 학습 폴더에서 찾으면 해시가 조용히 빠진다."""
    _fake_split(tmp_path, monkeypatch, ["a", "b"], ["c"], ["a", "b"], ["c"])
    rec = M.split_record(hash_images=True)
    assert rec["complete"] is True
    assert set(rec["image_hashes"]) == {"train/a", "train/b", "val/c"}


def test_same_name_in_both_splits_keeps_two_entries(tmp_path, monkeypatch):
    """같은 이름이 양쪽 목록에 있어도 항목이 하나로 뭉치면 안 된다."""
    _fake_split(tmp_path, monkeypatch, ["x"], ["x"], ["x"], ["x"])
    rec = M.split_record(hash_images=True)
    assert set(rec["image_hashes"]) == {"train/x", "val/x"}


def test_image_found_in_the_other_directory_is_recorded(tmp_path, monkeypatch):
    """**논리적 분할과 파일이 놓인 자리는 다르다.**

    학습 목록의 프레임이 images/val에 있기도 한다 — 물리적 배치는 내려받기
    단계가 정하고 분할은 시드가 정하기 때문이다. 실제 COCO 산출물이 그랬고,
    한쪽만 찾던 판은 190장을 조용히 빠뜨렸다.
    """
    # 'b'는 학습 목록인데 파일은 val 폴더에만 있다.
    _fake_split(tmp_path, monkeypatch, ["a", "b"], ["c"], ["a"], ["b", "c"])
    rec = M.split_record(hash_images=True)
    assert rec["complete"] is True, rec.get("missing_images")
    assert rec["image_locations"]["train/b"] == "images/val"
    assert rec["image_locations"]["train/a"] == "images/train"


def test_missing_images_are_named_not_skipped(tmp_path, monkeypatch):
    """빠진 것이 있으면 완전하지 않다고 말하고 무엇이 빠졌는지 적는다."""
    _fake_split(tmp_path, monkeypatch, ["a", "b"], ["c"], ["a"], [])
    rec = M.split_record(hash_images=True)
    assert rec["complete"] is False
    assert sorted(rec["missing_images"]) == ["train/b", "val/c"]


def test_skipping_hashes_is_not_complete(tmp_path, monkeypatch):
    """해시를 안 떴으면 완전하다고 말할 수 없다."""
    _fake_split(tmp_path, monkeypatch, ["a"], ["b"], ["a"], ["b"])
    rec = M.split_record(hash_images=False)
    assert rec["complete"] is False
    assert "complete_reason" in rec


def test_weight_source_is_unknown_when_not_given(tmp_path, monkeypatch):
    """출처를 모르면 추측하지 않는다."""
    monkeypatch.setattr(M.config, "EXPERIMENT_ROOT", tmp_path)
    assert M.weights_record(["runs_x/clean"])[0]["source"] == "unknown"


def test_weight_source_is_recorded_when_given(tmp_path, monkeypatch):
    monkeypatch.setattr(M.config, "EXPERIMENT_ROOT", tmp_path)
    rec = M.weights_record(["runs_x/clean"], {"runs_x/clean": "train_coco_rulers.sh"})
    assert rec[0]["source"] == "train_coco_rulers.sh"


def test_manifest_declares_its_schema_version(tmp_path, monkeypatch):
    _fake_split(tmp_path, monkeypatch, ["a"], ["b"], ["a"], ["b"])
    monkeypatch.setattr(M.config, "EXPERIMENT_ROOT", tmp_path)
    assert M.build([], hash_images=False)["manifest_schema_version"] == M.MANIFEST_SCHEMA_VERSION


def test_dirty_tree_is_marked_not_reproducible():
    """dirty 여부만 적으면 재현 가능한 줄 안다."""
    state = M.git_state()
    if state["clean"] is False:
        assert state["reproducible"] is False
        assert "reproducible_reason" in state
        # diff 해시는 대조용이지 재현 수단이 아니다 — 내용은 어디에도 안 남는다.
        assert "uncommitted_diff_sha256" in state
