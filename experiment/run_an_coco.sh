#!/bin/sh
# AN을 COCO에서 확인한다 (docs/22 계획 1번).
# KITTI 안에서만 쟀는데, 진짜 도메인 이동은 COCO다(AI).
set -e
cd "$(dirname "$0")"
export AIDA_DATASET=coco
for s in 42 123 2024; do
  echo "########## COCO seed $s ##########"
  ./venv/Scripts/python.exe rank_systematic_first.py --seed $s \
    --kinds coco_self kitti_on_coco --matched-kind coco_self \
    --out rank_fix_coco_seed$s.json
done
echo "=== 전부 완료 ==="
