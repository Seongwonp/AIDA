"""자기 정제 — 휘어진 자로 깨끗한 부분집합을 골라 자를 다시 만든다.

V에서 확인한 것: 고객 데이터로 학습한 모델("self 자")은 개별 오류를 짚는 데는
약하다(재현율 82% → 50%). 그런데 **이미지를 깨끗한 순으로 줄 세우는 건 거의
그대로 해낸다** — 가장 깨끗한 50%를 고르면 전체 오류의 20.9%만 딸려온다
(clean 자는 19.3%, 무작위면 50%). 선택이 탐지보다 쉬운 과제이기 때문이다.

그래서: self 자로 깨끗한 부분집합을 고르고 → 그것만으로 재학습하고 → 그 모델을
새 자로 쓴다. 오류율 30%짜리 전체 대신 12%짜리 절반으로 학습하는 셈이다.

교환이 있다. 이미지가 절반이 되므로 모델 자체가 약해진다. 오류가 줄어드는
이득이 데이터가 주는 손해보다 큰지가 이 실험의 질문이다.

사용법:
  python refine_ruler.py --condition scale_m30 --keep 0.5
  → conditions_<...>/scale_m30_refined50 생성 (학습은 run_all.py로)
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import config
from diagnose_labels import run
from error_injector import symlink_files, write_data_yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description="자기 정제용 부분집합 생성")
    parser.add_argument("--condition", required=True)
    parser.add_argument("--keep", type=float, default=0.5,
                        help="가장 깨끗한 상위 몇 %%를 남길지 (0.5 = 절반)")
    args = parser.parse_args()

    root = config.CONDITIONS_DIR / args.condition
    if not root.is_dir():
        raise SystemExit(f"{root} 없음")
    ruler = config.RUNS_DIR / args.condition / "weights" / "best.pt"
    if not ruler.exists():
        raise SystemExit(f"{ruler} 없음 — 이 조건을 먼저 학습하세요 (self 자가 필요)")

    images_dir = root / "images" / "train"
    findings, _total = run(images_dir, root / "labels" / "train", weights=ruler)

    # 의심 건수가 적은 이미지부터. 같으면 이름 순 — 시드 없이 재현되게.
    suspicion = Counter(f.image for f in findings)
    names = sorted(p.name for p in images_dir.iterdir())
    ranked = sorted(names, key=lambda n: (suspicion.get(n, 0), n))
    k = max(1, int(len(ranked) * args.keep))
    kept = {Path(n).stem for n in ranked[:k]}

    tag = f"{args.condition}_refined{int(args.keep * 100)}"
    out = config.CONDITIONS_DIR / tag
    # 남긴 프레임만 링크한다. 라벨은 조건 것 그대로 — 정제는 "어느 이미지를
    # 쓸지"만 고르지 라벨을 고치지 않는다. 고치려면 정답을 알아야 한다.
    symlink_files(images_dir, out / "images" / "train", kept)
    symlink_files(root / "labels" / "train", out / "labels" / "train", kept)
    val_stems = {p.stem for p in config.LABELS_GT_VAL_DIR.glob("*.txt")}
    symlink_files(config.IMAGES_VAL_DIR, out / "images" / "val", val_stems)
    symlink_files(config.LABELS_GT_VAL_DIR, out / "labels" / "val", val_stems)
    yaml_path = write_data_yaml(out)

    kept_sus = sum(suspicion.get(n, 0) for n in ranked[:k])
    print(f"[{tag}] 이미지 {len(names)} → {k}장 (의심 {sum(suspicion.values())} → {kept_sus}건)")
    print(f"  → {out}\n  → {yaml_path}")


if __name__ == "__main__":
    main()
