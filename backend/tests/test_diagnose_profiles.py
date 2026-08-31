"""클래스 구성별 성능 패턴 DB.

재검수 우선순위는 "이 오류 유형이 mAP를 얼마나 떨어뜨리는가"에 기댄다.
그 저하폭은 클래스 구성마다 다르므로(docs/21 L), 어느 DB를 볼지 정해져야 한다.
"""
import pytest

from app.routers import report


def test_default_reads_the_car_database():
    assert report._metrics_path_for([]).name == "metrics.csv"
    assert report._metrics_path_for(["Car"]).name == "metrics.csv"


def test_multiclass_reads_its_own_database():
    assert report._metrics_path_for(["Car", "Van"]).name == "metrics_mc.csv"


def test_missing_database_is_a_404_not_a_crash(client):
    """그 구성의 학습이 아직 안 끝났으면 500이 아니라 없다고 말해야 한다."""
    r = client.get("/api/diagnose", params={"profile_classes": "Bird,Plane"})
    assert r.status_code in (200, 404)
    if r.status_code == 404:
        assert "metrics_mc.csv" in r.json()["detail"]


def test_default_diagnose_still_works(client):
    rows = client.get("/api/diagnose").json()["error_reports"]
    assert rows and all(r["review_priority"] in ("높음", "중간", "낮음") for r in rows)


def test_class_swap_has_a_korean_label():
    """다중 클래스 표에 나오는 유형인데 라벨이 없으면 화면에 영문 키가 뜬다."""
    assert report.TYPE_LABELS["class_swap"] == "클래스 오기입"
