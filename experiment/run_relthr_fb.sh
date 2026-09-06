#!/bin/sh
set -e
cd "$(dirname "$0")"
for s in 42 123 2024; do
  AIDA_DATASET=coco ./venv/Scripts/python.exe relative_threshold.py --seed $s --mode fallback \
    --kinds coco_self kitti_on_coco --matched-kind coco_self --out relfb_coco_$s.json
done
for s in 42 123; do
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_FRAME_SELECT=cyclist_rich \
    ./venv/Scripts/python.exe relative_threshold.py --seed $s --mode fallback \
    --kinds matched brich shifted broad --matched-kind matched --out relfb_kitti_$s.json
done
echo "=== 전부 완료 ==="
