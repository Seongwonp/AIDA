"""서버가 붙이는 고유 오류 id(`<이미지>/L<라벨>`)로 짝지은 부트스트랩이 도는가.

prelim1 판정 전 합성 판정으로 집계 경로를 돌려 보다가 잡혔다. 재표집이 이미지를
`a.jpg#0`으로, 오류 id를 `a.jpg/L0#0`으로 따로 바꿔서, 스키마 규칙
(`unique_error_id == f"{image_id}/L{label_index}"`)에 걸려 **실제 내보내기로는
부트스트랩이 한 번도 돌지 않았다.** 기존 검사는 이 모양의 id를 부트스트랩에 넣은
적이 없었다.
"""
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
