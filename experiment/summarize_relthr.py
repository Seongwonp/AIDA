"""AO(상대 문턱으로의 후퇴)를 시드별로 모아 미리 정한 기준으로 판정한다.

`PREDICTION_ao_seeds.md`에 적어둔 1차 기준:

    맞는 자 측정 중 @5 변화가 −0.02보다 나쁜 것이 몇 개인가
      3개 이상 → 손해가 실재한다 (조건부로 끄는 것을 검토)
      1~2개    → 드물다 (빈도를 수치로 적고 유지)
      0개      → −0.038은 흔들림이었다

**결과를 보고 기준을 바꾸지 않는다.** 그래서 문턱을 이 파일 위쪽에 상수로 둔다.

사용법:
  python summarize_relthr.py                 # relfb_*.json 전부
  python summarize_relthr.py --glob 'relthr_*.json'
"""
import argparse
import io
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
HARM = -0.02   # 맞는 자에서 이보다 나쁘면 "손해"로 센다 (AO에서 미리 정한 선)
GAIN = 0.05    # 어긋난 자에서 이 이상이면 "이득이 유지된다"


def load(pattern: str) -> list[dict]:
    out = []
    for f in sorted(HERE.glob(pattern)):
        d = json.load(io.open(f, encoding="utf-8"))
        d["_file"] = f.name
        out.append(d)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="AO 시드 결과를 미리 정한 기준으로 판정")
    ap.add_argument("--glob", default="relfb_*.json")
    args = ap.parse_args()

    runs = load(args.glob)
    if not runs:
        raise SystemExit(f"{args.glob}에 맞는 파일이 없습니다")

    matched, mismatched = [], []
    for d in runs:
        for row in d["rows"]:
            delta = row["with_relative"]["5"] - row["an_only"]["5"]
            rec = (d["seed"], row["kind"], row["label"], delta,
                   row["an_only"]["5"], row["with_relative"]["5"],
                   row["empty_absolute"], row["n_conditions"])
            (matched if row["kind"] == d["matched_kind"] else mismatched).append(rec)

    for title, rows in (("맞는 자 (1차 기준)", matched), ("어긋난 자 (2차)", mismatched)):
        print(f"\n■ {title} — 측정 {len(rows)}개")
        print(f"  {'시드':>6}  {'자':<16}{'@5 전':>8}{'@5 후':>8}{'변화':>9}"
              f"{'절대문턱 빈 조건':>16}")
        for seed, _kind, label, delta, before, after, empty, n in sorted(rows):
            flag = "  ←" if delta < HARM else ""
            print(f"  {seed:>6}  {label:<16}{before:>8.3f}{after:>8.3f}"
                  f"{delta:>+9.3f}{f'{empty}/{n}':>16}{flag}")

    harms = [r for r in matched if r[3] < HARM]
    print(f"\n1차 판정 — 맞는 자 {len(matched)}개 중 {HARM}보다 나쁜 것: "
          f"**{len(harms)}개**")
    if len(harms) >= 3:
        print("  → 손해가 실재한다. 조건부로 끄는 것을 검토한다.")
    elif harms:
        print("  → 드물다. 방침을 유지하되 빈도를 수치로 적는다.")
    else:
        print("  → 없다. AO의 기준 미달이 해소된다.")
    if matched:
        avg = sum(r[3] for r in matched) / len(matched)
        worst = min(r[3] for r in matched)
        zero = sum(1 for r in matched if r[3] == 0.0)
        print(f"     평균 {avg:+.4f}, 최악 {worst:+.3f}, 변화 없음 {zero}/{len(matched)}")

    if mismatched:
        avg = sum(r[3] for r in mismatched) / len(mismatched)
        pos = sum(1 for r in mismatched if r[3] > 0)
        print(f"\n2차 — 어긋난 자 {len(mismatched)}개 중 양수 {pos}개, 평균 {avg:+.3f}")
        print(f"  → 이득이 {'유지된다' if avg >= GAIN else '유지되지 않는다'} "
              f"(선 {GAIN})")


if __name__ == "__main__":
    main()
