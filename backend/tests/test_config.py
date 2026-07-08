from app.config import _split_csv


def test_split_csv_single_origin():
    assert _split_csv("http://localhost:5173") == ["http://localhost:5173"]


def test_split_csv_multiple_origins_trims_whitespace():
    assert _split_csv("http://a.com, http://b.com,http://c.com") == [
        "http://a.com",
        "http://b.com",
        "http://c.com",
    ]


def test_split_csv_ignores_empty_segments():
    assert _split_csv("http://a.com,,") == ["http://a.com"]
