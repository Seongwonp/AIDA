"""판정자 간 일치도 (사전 등록 D8).

**무엇을 세는가를 이름으로 가른다.** 분모가 다른 수를 한 이름으로 부르면 나중에 어느
것이었는지 사라진다.

    both_judged        두 판정자 모두 판정(보류 포함)한 후보 — 3분류 일치율·κ의 분모
    both_decided       두 판정자 모두 hit/miss로 결정한 후보 — 2분류 일치율·κ의 분모

κ는 Cohen의 단순 κ다. 가중 없음. 표본이 작으면 κ는 불안정하고, 여기서는 **합격선을
두지 않는다** — 낮아도 그대로 공개한다.
"""
from collections import Counter

VERDICTS = ("hit", "miss", "hold")


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """(판정자1, 판정자2) 쌍의 Cohen κ. 쌍이 없거나 기대 일치가 1이면 None."""
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if pe >= 1.0:
        return None
    return round((po - pe) / (1 - pe), 4)


def agreement_report(sample_ids: list[str], primary: dict[str, str | None],
                     secondary: dict[str, str | None]) -> dict:
    """보조 표본에서 두 판정자의 일치도. 입력은 후보 id → 판정(없으면 None)."""
    ids = sorted(sample_ids)
    p = {i: primary.get(i) for i in ids}
    s = {i: secondary.get(i) for i in ids}
    both = [i for i in ids if p[i] in VERDICTS and s[i] in VERDICTS]
    decided = [i for i in both if p[i] != "hold" and s[i] != "hold"]
    pairs3 = [(p[i], s[i]) for i in both]
    pairs2 = [(p[i], s[i]) for i in decided]
    matrix = Counter(pairs3)
    return {
        "sample_size": len(ids),
        "primary_judged": sum(1 for i in ids if p[i] in VERDICTS),
        "secondary_judged": sum(1 for i in ids if s[i] in VERDICTS),
        "primary_holds": sum(1 for i in ids if p[i] == "hold"),
        "secondary_holds": sum(1 for i in ids if s[i] == "hold"),
        "both_judged": len(both),
        "both_decided": len(decided),
        "agreement_3way": {
            "denominator": "both_judged (hit/miss/hold 3분류)",
            "n": len(both),
            "agree": sum(1 for a, b in pairs3 if a == b),
            "rate": (round(sum(1 for a, b in pairs3 if a == b) / len(both), 4) if both else None),
            "kappa": cohen_kappa(pairs3),
        },
        "agreement_decided": {
            "denominator": "both_decided (양쪽 모두 hit/miss, hold 제외 2분류)",
            "n": len(decided),
            "agree": sum(1 for a, b in pairs2 if a == b),
            "rate": (round(sum(1 for a, b in pairs2 if a == b) / len(decided), 4) if decided else None),
            "kappa": cohen_kappa(pairs2),
        },
        "confusion_primary_x_secondary": {f"{a}/{b}": matrix[(a, b)] for a in VERDICTS for b in VERDICTS
                                         if matrix[(a, b)]},
        "note": "일치율 합격선은 두지 않는다. 1차 분석은 primary의 원본 판정이며 불일치로 수정하지 않는다.",
    }
