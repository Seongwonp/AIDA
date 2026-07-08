def test_diagnose_excludes_clean_and_groups_by_type(client):
    body = client.get("/api/diagnose").json()
    error_types = {r["error_type"] for r in body["error_reports"]}
    assert error_types == {"width", "height", "rotation"}


def test_diagnose_priority_thresholds(client):
    """report.py 기준: >=15% 높음, 8~15% 중간, <8% 낮음.

    fixtures/metrics.csv는 각 유형의 max_performance_drop_pct가 정확히
    15.0(width_big) / 8.0(height_small) / 0.0(rot_test)이 되도록 설계되어
    경계값에서 분류가 정확한지 확인한다.
    """
    body = client.get("/api/diagnose").json()
    by_type = {r["error_type"]: r for r in body["error_reports"]}

    assert by_type["width"]["max_performance_drop_pct"] == 15.0
    assert by_type["width"]["review_priority"] == "높음"

    assert by_type["height"]["max_performance_drop_pct"] == 8.0
    assert by_type["height"]["review_priority"] == "중간"

    assert by_type["rotation"]["max_performance_drop_pct"] == 0.0
    assert by_type["rotation"]["review_priority"] == "낮음"


def test_diagnose_sorted_by_drop_descending(client):
    body = client.get("/api/diagnose").json()
    drops = [r["max_performance_drop_pct"] for r in body["error_reports"]]
    assert drops == sorted(drops, reverse=True)


def test_diagnose_labels_are_korean(client):
    body = client.get("/api/diagnose").json()
    by_type = {r["error_type"]: r["label"] for r in body["error_reports"]}
    assert by_type["width"] == "가로 길이 오류"
    assert by_type["height"] == "세로 길이 오류"
    assert by_type["rotation"] == "회전각 오류"
