"""서버가 붙이는 고유 오류 id(`<이미지>/L<라벨>`)로 짝지은 부트스트랩이 도는가.

prelim1 판정 전 합성 판정으로 집계 경로를 돌려 보다가 잡혔다. 재표집이 이미지를
`a.jpg#0`으로, 오류 id를 `a.jpg/L0#0`으로 따로 바꿔서, 스키마 규칙
(`unique_error_id == f"{image_id}/L{label_index}"`)에 걸려 **실제 내보내기로는
부트스트랩이 한 번도 돌지 않았다.** 기존 검사는 이 모양의 id를 부트스트랩에 넣은
적이 없었다.
"""
import evaluation.bootstrap as bootstrap_module
from evaluation.bootstrap import paired_cluster_bootstrap
from evaluation.schema import Adjudication, Ranking


def _world():
    """이미지 둘. 이미지마다 hit 하나(라벨 0), miss 하나(라벨 1).

    AIDA는 hit을 위로(0.9 > 0.1), 기준선은 miss를 위로(0.9 > 0.1) 둔다.
    """
    facts, ranks = [], []
    for image in ("a.jpg", "b.jpg"):
        hit = Adjudication("ds", image, "c0", "width", "hit", 0, f"{image}/L0")
        miss = Adjudication("ds", image, "c1", "width", "miss", 1, None)
        facts += [hit, miss]
        ranks += [Ranking("aida", hit.key, 0.9), Ranking("aida", miss.key, 0.1),
                  Ranking("iou_baseline", hit.key, 0.1), Ranking("iou_baseline", miss.key, 0.9)]
    return facts, ranks


def test_서버_형식의_오류_id로도_부트스트랩이_돈다():
    """손계산 (검수량 2).

    재표집은 이미지 묶음 2개를 복원추출한다. 어느 두 개가 뽑히든
    AIDA 상위 2건 = hit 2건 = 고유 오류 2개, 기준선 상위 2건 = miss 2건 = 0개.
    **같은 이미지가 두 번 뽑혀도** 두 벌은 다른 관측이라 고유 오류는 2개다.
    그러니 모든 재표본에서 차이는 정확히 2 → 구간 [2, 2].
    """
    facts, ranks = _world()
    got = paired_cluster_bootstrap(facts, ranks, "aida", "iou_baseline", budget=2,
                                   iterations=200, seed=42)
    assert got["observed_difference"] == 2
    assert got["ci_low"] == 2.0
    assert got["ci_high"] == 2.0


def test_두_방법이_같은_재표본_묶음을_본다(monkeypatch):
    """짝지음: 재표본마다 AIDA와 기준선이 **같은 후보 벌**에 점수를 매겨야 한다.

    따로 뽑으면 차이의 분포가 아니라 두 독립 분포의 차이가 된다.
    """
    seen = []
    real = bootstrap_module._resample

    def spy(*args, **kwargs):
        facts, ranks = real(*args, **kwargs)
        keys = {m: {r.candidate_key for r in ranks if r.method == m} for m in ("aida", "iou_baseline")}
        seen.append((keys["aida"] == keys["iou_baseline"] == {a.key for a in facts}, len(facts)))
        return facts, ranks

    monkeypatch.setattr(bootstrap_module, "_resample", spy)
    facts, ranks = _world()
    paired_cluster_bootstrap(facts, ranks, "aida", "iou_baseline", budget=2, iterations=50, seed=42)
    assert len(seen) == 50
    assert all(same for same, _ in seen)
    assert all(n == 4 for _, n in seen)          # 이미지 2개 × 후보 2건씩 뽑힌다


def test_누락_층_형식의_id도_중복_추출에서_따로_센다():
    """누락 객체 id는 서버가 `<이미지>/M<번호>`로 붙인다. 같은 이미지가 두 번 뽑혀도
    두 벌은 다른 누락 객체다.

    손계산은 위 검사와 같다 (검수량 2): 모든 재표본에서 AIDA 2개, 기준선 0개 → 차이 2.
    """
    facts, ranks = [], []
    for image in ("a.jpg", "b.jpg"):
        hit = Adjudication("ds", image, "m0", "missing", "hit", None, f"{image}/M1")
        miss = Adjudication("ds", image, "m1", "missing", "miss", None, None)
        facts += [hit, miss]
        ranks += [Ranking("aida", hit.key, 0.9), Ranking("aida", miss.key, 0.1),
                  Ranking("iou_baseline", hit.key, 0.1), Ranking("iou_baseline", miss.key, 0.9)]
    got = paired_cluster_bootstrap(facts, ranks, "aida", "iou_baseline", budget=2,
                                   iterations=200, seed=42)
    assert (got["observed_difference"], got["ci_low"], got["ci_high"]) == (2, 2.0, 2.0)

