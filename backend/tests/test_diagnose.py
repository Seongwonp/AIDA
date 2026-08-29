def test_diagnose_excludes_clean_and_groups_by_type(client):
    body = client.get("/api/diagnose").json()
    error_types = {r["error_type"] for r in body["error_reports"]}
    assert error_types == {"width", "height", "rotation", "scale"}


def test_diagnose_priority_is_relative_to_worst_observed_drop(client):
    """고정 %가 아니라 "관측된 최대 저하 대비 비율"로 등급을 매긴다.

    예전에는 15%/8% 고정값이라 실측(최대 저하 6%대)에서는 전 유형이
    "낮음"으로만 나왔다. 상대 기준이면 성능 패턴 DB가 갱신돼도 등급이
    같이 따라간다.

    fixture: width_big 15%(최대) / height_mid 6% / scale_tiny 1%
    """
    body = client.get("/api/diagnose").json()
    by_type = {r["error_type"]: r for r in body["error_reports"]}

    # 최대 저하 자신 → 높음 (100%)
    assert by_type["width"]["max_performance_drop_pct"] == 15.0
    assert by_type["width"]["review_priority"] == "높음"

    # 최대의 40% → 중간
    assert by_type["height"]["review_priority"] == "중간"

    # 최대의 6.7% → 낮음
    assert by_type["scale"]["review_priority"] == "낮음"


def test_diagnose_demotes_drop_within_seed_noise(client):
    """시드 간 편차와 구분되지 않는 저하는 크기가 커도 "낮음"이어야 한다.

    없는 문제에 검수 예산을 쓰게 만들면 안 된다. fixture의 rot_noise는
    저하 6.67%로 height_mid(6%)보다 큰데, 표준편차가 5%p라 1.3σ에 불과하다.
    크기만 보면 "중간"이 되겠지만 통계적으로는 노이즈다.
    """
    body = client.get("/api/diagnose").json()
    by_type = {r["error_type"]: r for r in body["error_reports"]}

    rot = by_type["rotation"]
    assert rot["max_performance_drop_pct"] > by_type["height"]["max_performance_drop_pct"]
    assert rot["review_priority"] == "낮음"
    assert "구분되지 않습니다" in rot["priority_rationale"]


def test_diagnose_explains_every_priority(client):
    """등급만 주면 고객이 "왜 이게 높음인가"를 확인할 수 없다."""
    body = client.get("/api/diagnose").json()
    for report in body["error_reports"]:
        assert report["priority_rationale"], report["error_type"]


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
    assert by_type["scale"] == "스케일 오류"
