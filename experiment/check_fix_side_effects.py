"""재검수 시뮬레이션의 '고치기'가 엉뚱한 GT에 붙는지 확인한다 (학습 불필요).

T에서 상위 50%를 고친 결과가 25%보다 낮게 나왔다 — 세 정렬 모두에서. 더
고쳤는데 덜 회복되는 건 원리적으로 이상하다. 의심 후보는 `simulate_review`의
`_best_gt`다: 지목된 박스와 IoU가 가장 큰 GT로 되돌리는데, 밀집 장면에서는
이웃 GT가 더 크게 겹칠 수 있다. 그러면 멀쩡한 라벨을 이웃 것으로 바꿔놓아
**고칠수록 나빠진다.**

scale_m30은 라벨과 GT가 1:1 대응이다(누락·중복 주입이 없어 줄 수와 순서가
그대로다). 그래서 "라벨 i를 고칠 때 GT i로 갔는가"를 인덱스로 정확히 잴 수 있다.

사용법:
  python check_fix_side_effects.py
"""
import json
import sys
from collections import Counter

from PIL import Image

import config
from diagnose_labels import load_yolo_labels_with_classes
from label_diagnosis import iou
from simulate_review import FIX_MATCH_IOU, _best_gt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "scale_m30"
VARIANTS = [f"{BASE}_fix_{o}_{p}" for o in ("severity", "class_weighted", "random")
            for p in (25, 50)]


def main() -> None:
    src = config.CONDITIONS_DIR / BASE / "labels" / "train"
    record = json.loads(
        (config.CONDITIONS_DIR / BASE / "injection_record.json").read_text(encoding="utf-8"))

    stats = Counter()
    worst_examples = []

    for label_path in sorted(src.glob("*.txt")):
        img = config.IMAGES_TRAIN_DIR / f"{label_path.stem}.png"
        with Image.open(img) as im:
            w, h = im.width, im.height
        gt, _gtc = load_yolo_labels_with_classes(
            config.LABELS_GT_TRAIN_DIR / label_path.name, w, h)
        cur, _cc = load_yolo_labels_with_classes(label_path, w, h)
        if len(gt) != len(cur):
            stats["줄 수 불일치(집계 제외)"] += 1
            continue
        errored = set(record.get(label_path.stem, {}).get("errored", []))

        for i, box in enumerate(cur):
            picked = _best_gt(box, gt)
            is_error = i in errored
            key = "오류 라벨" if is_error else "멀쩡한 라벨"
            if picked is None:
                stats[f"{key} · 대응 GT 못 찾음(삭제됨)"] += 1
            elif picked == i:
                stats[f"{key} · 제 짝으로 복원"] += 1
            else:
                stats[f"{key} · 엉뚱한 GT로 교체"] += 1
                if len(worst_examples) < 5:
                    worst_examples.append(
                        (label_path.stem, i, picked,
                         round(iou(box, gt[i]), 3), round(iou(box, gt[picked]), 3)))

    print(f"{BASE}의 모든 라벨에 대해 '고치면 어디로 가는가'를 계산\n")
    total = sum(v for k, v in stats.items() if "제외" not in k)
    for k in sorted(stats):
        print(f"  {k:<34}{stats[k]:>6}  ({stats[k]/total*100:>5.2f}%)")

    bad = sum(v for k, v in stats.items() if "엉뚱한" in k or "못 찾음" in k)
    print(f"\n잘못 붙거나 삭제되는 비율: {bad}/{total} = {bad/total*100:.2f}%")

    if worst_examples:
        print("\n예시 (프레임, 라벨idx → 선택된 GTidx, 제짝IoU, 선택IoU)")
        for e in worst_examples:
            print(f"  {e[0]}  {e[1]} → {e[2]}   제짝 {e[3]}  선택 {e[4]}")
    else:
        print("\n엉뚱한 GT로 가는 사례 없음")

    print(f"\n(IoU 문턱 {FIX_MATCH_IOU} 미만이면 '대응 GT 없음'으로 보고 그 줄을 지운다)")


if __name__ == "__main__":
    main()
