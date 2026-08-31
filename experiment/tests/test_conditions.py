

# ── 클래스 구성별 경로 분리 ──────────────────────────────────────────────────
# 클래스 구성이 바뀌면 라벨·가중치·지표가 전부 다른 실험이 된다. 조건 이름은
# 그대로라(width_m30 등) 경로를 안 나누면 한쪽이 다른 쪽을 덮어쓴다.

def _paths_for(classes: str, monkeypatch) -> dict:
    import importlib
    import config as config_module
    monkeypatch.setenv("AIDA_CLASSES", classes)
    reloaded = importlib.reload(config_module)
    out = {
        "conditions": reloaded.CONDITIONS_DIR.name,
        "runs": reloaded.RUNS_DIR.name,
        "metrics": reloaded.METRICS_CSV.name,
        "multi_seed": reloaded.MULTI_SEED_CSV.name,
        "agg": reloaded.AGG_CSV.name,
        "labels_gt": reloaded.LABELS_GT_TRAIN_DIR.parent.name,
    }
    monkeypatch.delenv("AIDA_CLASSES", raising=False)
    importlib.reload(config_module)
    return out


def test_single_class_paths_are_unchanged(monkeypatch):
    """Car 단일 결과(docs/21 A~K)의 경로가 그대로여야 재현성이 유지된다."""
    p = _paths_for("Car", monkeypatch)
    assert p == {
        "conditions": "conditions", "runs": "runs", "metrics": "metrics.csv",
        "multi_seed": "metrics_multi_seed.csv", "agg": "metrics_agg.csv",
        "labels_gt": "labels_gt",
    }


def test_multiclass_paths_are_all_separated(monkeypatch):
    """하나라도 안 나뉘면 그쪽으로 Car 결과가 덮인다.

    특히 multi_seed는 (error_seed, condition)으로 병합해서, 겹치면 오류도
    안 나고 조용히 사라진다.
    """
    p = _paths_for("Car,Van,Pedestrian,Cyclist", monkeypatch)
    single = _paths_for("Car", monkeypatch)
    assert all(p[k] != single[k] for k in p), f"안 나뉜 경로가 있음: {p}"


# ── 이미지/라벨 개수 일치 ────────────────────────────────────────────────────
# data/processed/images/는 클래스 구성·프레임 선택과 무관하게 공유되고
# data_loader를 돌릴 때마다 쌓인다. 반면 라벨은 구성별로 갈린다. 폴더를 통째로
# 링크하면 라벨 없는 이미지가 딸려 들어가고 ultralytics는 그걸 "객체 없는
# 배경"으로 학습한다 — 오류 없이 조용히. cyclist_rich 실험이 실제로 이미지
# 777장에 라벨 400개로 학습돼 결과가 통째로 무효가 됐다(docs/21 S 정정).

def test_symlink_files_links_only_requested_stems(tmp_path):
    from error_injector import symlink_files

    src = tmp_path / "src"; src.mkdir()
    for name in ("a.png", "b.png", "c.png"):
        (src / name).write_bytes(b"x")
    dst = tmp_path / "dst"
    symlink_files(src, dst, only_stems={"a", "b"})
    assert sorted(p.stem for p in dst.iterdir()) == ["a", "b"]


def test_symlink_files_removes_stale_links(tmp_path):
    """구성이 바뀌어 다시 만들 때, 예전에 잘못 걸린 링크가 남으면 안 된다."""
    from error_injector import symlink_files

    src = tmp_path / "src"; src.mkdir()
    for name in ("a.png", "b.png"):
        (src / name).write_bytes(b"x")
    dst = tmp_path / "dst"
    symlink_files(src, dst, only_stems={"a", "b"})
    symlink_files(src, dst, only_stems={"a"})
    assert sorted(p.stem for p in dst.iterdir()) == ["a"]
