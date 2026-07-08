def test_summary_shape(client):
    response = client.get("/api/summary")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "total_images",
        "total_objects",
        "suspected_error_count",
        "quality_score",
        "certified",
    }
    assert isinstance(body["total_images"], int)
    assert isinstance(body["quality_score"], int)
    assert 0 <= body["quality_score"] <= 100
    assert isinstance(body["certified"], bool)
