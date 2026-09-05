"""broad 1000장을 Cyclist 수로 갈라 자 세 대의 프레임 목록을 만든다 (docs/22 계획 1번).

AL은 클래스 구성이 같은 어긋난 자 짝이 **하나뿐**이라 "적합도는 클래스 구성이
같을 때만 비교 가능하다"를 확인할 수 없었다. 짝을 늘리려면 4클래스 자가 더
있어야 한다.

**broad 풀을 쓰는 이유는 누수 때문이다.** 평가는 cyclist_rich 프레임에서
하는데 broad와 cyclist_rich는 겹침이 0이다(확인함). broad 안에서 어떻게 갈라도
평가 데이터를 미리 본 자가 되지 않는다.

**Cyclist 수로 가르는 이유.** broad 1000장에 Cyclist가 76개뿐이고 928장은
0개다. 위에서 500장을 자르면 76개를 다 갖고, 아래 500장은 하나도 없다.
평가 데이터(cyclist_rich)는 라벨의 20%가 Cyclist라, 이 차이가 실제 진단
품질 차이로 이어질 것이다 — 그래야 "적합도가 그 차이를 아는가"를 물을 수 있다.

가운데(mid)는 정렬 목록에서 한 칸씩 건너뛴 500장이다. rich·poor와 겹치므로
더 비슷한 자가 되고, 그게 **더 어려운 시험**이라 일부러 넣는다.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW = Path("data/raw")
LABELS = RAW / "labels" if (RAW / "labels").is_dir() else RAW / "training" / "label_2"
N = 500          # N_TRAIN 400 + N_VAL 100

frames = (RAW / "selected_frames_broad.txt").read_text().split()
counted = []
for stem in frames:
    p = LABELS / f"{stem}.txt"
    if not p.exists():
        continue
    n = sum(1 for line in p.read_text().splitlines() if line.startswith("Cyclist "))
    counted.append((n, stem))
# Cyclist 많은 순, 같으면 이름 순 — 시드 없이도 재현되게 (cyclist_rich와 같은 방식)
counted.sort(key=lambda x: (-x[0], x[1]))

splits = {
    "broad_rich": counted[:N],
    "broad_poor": counted[-N:],
    "broad_mid": counted[::2][:N],
}
for name, chosen in splits.items():
    out = RAW / f"selected_frames_{name}.txt"
    out.write_text("\n".join(sorted(s for _n, s in chosen)) + "\n", encoding="utf-8")
    print(f"{name:<12} {len(chosen)}장 · Cyclist {sum(n for n, _ in chosen):>3}개 → {out.name}")

rich = {s for _n, s in splits["broad_rich"]}
poor = {s for _n, s in splits["broad_poor"]}
print(f"\nrich ∩ poor = {len(rich & poor)}장 (0이어야 한다)")

cr = set((RAW / "selected_frames_cyclist_rich.txt").read_text().split())
for name, chosen in splits.items():
    overlap = len({s for _n, s in chosen} & cr)
    print(f"{name:<12} ∩ 평가셋(cyclist_rich) = {overlap}장 (0이어야 한다)")
