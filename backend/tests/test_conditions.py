def test_conditions_count_and_shape(client):
    response = client.get("/api/conditions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4  # fixtures/metrics.csv 행 수와 일치해야 함

    by_condition = {row["condition"]: row for row in body}
    assert set(by_condition) == {"clean", "width_big", "height_small", "rot_test"}


def test_clean_baseline_has_zero_drop(client):
    body = client.get("/api/conditions").json()
    clean = next(row for row in body if row["condition"] == "clean")
    assert clean["performance_drop_pct"] == 0.0
    assert clean["mean_iou"] == 1.0
    assert clean["mean_iou_drop_pct"] == 0.0


def test_performance_drop_pct_computed_relative_to_clean(client):
    body = client.get("/api/conditions").json()
    by_condition = {row["condition"]: row for row in body}

    # fixtures/metrics.csv: clean map50=0.900, width_big map50=0.765
    # (0.900 - 0.765) / 0.900 * 100 = 15.0
    assert by_condition["width_big"]["performance_drop_pct"] == 15.0

    # clean 0.900, height_small 0.828 → (0.900-0.828)/0.900*100 = 8.0
    assert by_condition["height_small"]["performance_drop_pct"] == 8.0

    # rot_test map50이 clean과 동일 → 저하 없음
    assert by_condition["rot_test"]["performance_drop_pct"] == 0.0


def test_iou_metrics_are_joined_by_condition(client):
    body = client.get("/api/conditions").json()
    by_condition = {row["condition"]: row for row in body}

    assert by_condition["width_big"]["mean_iou"] == 0.75
    assert by_condition["width_big"]["mean_iou_drop_pct"] == 25.0
    assert by_condition["rot_test"]["mean_iou"] == 0.7
    assert by_condition["rot_test"]["mean_iou_drop_pct"] == 30.0
