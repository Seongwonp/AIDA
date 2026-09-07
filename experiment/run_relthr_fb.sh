#!/bin/sh
# AO(절대 문턱이 못 잡을 때만 상대 문턱)를 자별·시드별로 잰다.
#
# 시드는 SEEDS로 바꾼다. 기본은 AF·AN이 쓴 7개다.
#   COCO_SEEDS  COCO 자기 도메인 자 (runs_coco에 학습된 것만)
#   KITTI_SEEDS KITTI 쪽 자 4대
set -e
cd "$(dirname "$0")"
for s in ${COCO_SEEDS:-42 123 2024 2025 31337 7 777}; do
  AIDA_DATASET=coco ./venv/Scripts/python.exe relative_threshold.py --seed $s --mode fallback \
    --kinds coco_self kitti_on_coco --matched-kind coco_self --out relfb_coco_$s.json
done
for s in ${KITTI_SEEDS:-42 123 2024 2025 31337 7 777}; do
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_FRAME_SELECT=cyclist_rich \
    ./venv/Scripts/python.exe relative_threshold.py --seed $s --mode fallback \
    --kinds matched brich shifted broad --matched-kind matched --out relfb_kitti_$s.json
done
echo "=== 전부 완료 ==="
