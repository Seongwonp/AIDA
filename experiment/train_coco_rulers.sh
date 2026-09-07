#!/bin/sh
# COCO 자기 도메인 자. KITTI 자와 대조해 **진짜 도메인 이동**을 잰다.
# Y~AH의 "도메인 이동"은 전부 KITTI 안에서의 프레임 선택 차이였다.
#
# 시드는 SEEDS로 바꾼다.  예: SEEDS="2025 31337 7 777" ./train_coco_rulers.sh
set -e
export AIDA_DATASET=coco
export AIDA_WORKERS=2
for ts in ${SEEDS:-42 123 2024}; do
  echo "=== COCO 자기 도메인 train_seed=$ts ==="
  if [ "$ts" = 42 ]; then
    ./venv/Scripts/python.exe train.py --condition clean
  else
    AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean
  fi
done
echo "=== 전부 완료 ==="
