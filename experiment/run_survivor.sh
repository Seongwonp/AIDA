#!/bin/sh
set -e
cd "$(dirname "$0")"
for s in 42 123 2024; do
  echo "########## COCO seed $s ##########"
  AIDA_DATASET=coco ./venv/Scripts/python.exe survivor_types.py --seed $s \
    --kinds kitti_on_coco coco_self --out survivor_coco_$s.json
done
echo "=== 전부 완료 ==="
