def test_roi_estimate_shape_and_totals(client):
    response = client.get("/api/roi-estimate")
    assert response.status_code == 200
    body = response.json()

    assert body["label"] == "추정 예시"
    assert body["assumptions"]["dataset_labels"] == 100_000
    assert body["manual_review_savings_krw"] > 0
    assert body["gpu_savings_krw"] > 0
    assert body["total_savings_krw"] == body["manual_review_savings_krw"] + body["gpu_savings_krw"]
    assert body["review_scope_reduction_pct"] == 70.0
