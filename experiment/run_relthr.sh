#!/bin/sh
set -e
cd "$(dirname "$0")"
for s in 42 123 2024; do
  echo "########## COCO seed $s ##########"
  AIDA_DATASET=coco ./venv/Scripts/python.exe relative_threshold.py --seed $s \
    --kinds coco_self kitti_on_coco --matched-kind coco_self \
    --out relthr_coco_$s.json
done
for s in 42 123; do
  echo "########## KITTI seed $s ##########"
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_FRAME_SELECT=cyclist_rich \
    ./venv/Scripts/python.exe relative_threshold.py --seed $s \
    --kinds matched brich shifted broad --matched-kind matched \
    --out relthr_kitti_$s.json
done
echo "=== 전부 완료 ==="
