"""오류 강도에 따라 상대 문턱 후퇴가 언제 손해인가 (docs/21 AW).

AV가 찾은 기제는 비율 싸움이다 — 자기 기하 오탐은 강도와 무관하게 쌓이는데
진짜 오류 지목은 강도에 비례한다. 그러면 **어느 강도 아래에서 잡음이 이기는지**
경계가 있어야 한다.

판정 기준은 `PREDICTION_error_intensity.md`에 먼저 적었다.

사용법:
  python analyze_intensity.py
"""
import argparse
import collections
import io
import json
import pathlib
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
HARM = -0.02   # 이보다 나쁘면 손해로 센다 (AO에서 미리 정한 선)


def main() -> None:
    ap = argparse.ArgumentParser(description="오류 강도별 후퇴 손익")
    ap.add_argument("--glob", default="intensity_*.json")
    args = ap.parse_args()

    # label -> kind_of_error -> pct -> [delta, ...]
    data: dict = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    for f in sorted(HERE.glob(args.glob)):
        d = json.load(io.open(f, encoding="utf-8"))
        for row in d["rows"]:
            for c in row.get("per_condition", []):
                kind, pct = c["condition"].rsplit("_", 1)
                data[row["label"]][kind][int(pct)].append(c["delta5"])
    if not data:
        raise SystemExit(f"{args.glob}에 맞는 파일이 없습니다")

    pcts = sorted({p for lab in data.values() for k in lab.values() for p in k})
    for label, kinds in data.items():
        print(f"\n■ {label}")
        print(f"  {'오류':<12}" + "".join(f"{str(p) + '%':>9}" for p in pcts))
        for kind, per_pct in kinds.items():
            cells = []
            for p in pcts:
                v = per_pct.get(p)
                cells.append("        —" if not v else f"{st.mean(v):>+9.3f}")
            print(f"  {kind:<12}" + "".join(cells))

    print("\n1차 — missing의 손해가 낮은 강도에만 몰리는가")
    ok = True
    for label, kinds in data.items():
        harmed = sorted(p for p, v in kinds.get("missing", {}).items()
                        if st.mean(v) < HARM)
        clean = sorted(p for p, v in kinds.get("missing", {}).items()
                       if st.mean(v) >= HARM)
        boundary = (max(harmed) < min(clean)) if harmed and clean else None
        print(f"  {label:<18} 손해 {harmed or '없음'} · 무해 {clean or '없음'}"
              f" → {'경계 있음' if boundary else '섞임' if boundary is False else '한쪽뿐'}")
        if boundary is False:
            ok = False
    print(f"  → {'경계가 있다' if ok else '경계가 없다 — 강도가 원인이 아니다'}")

    print("\n2차 — duplicate의 방향이 자에 따라 갈리는가")
    for label, kinds in data.items():
        vals = [st.mean(v) for _p, v in sorted(kinds.get("duplicate", {}).items())]
        pos = sum(1 for v in vals if v > 0)
        neg = sum(1 for v in vals if v < 0)
        print(f"  {label:<18} 양수 {pos} · 음수 {neg} · 0 {len(vals)-pos-neg}")


if __name__ == "__main__":
    main()
