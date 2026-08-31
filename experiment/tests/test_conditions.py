

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
