#!/bin/sh
set -e
cd "$(dirname "$0")"
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_FRAME_SELECT=nested
export AIDA_VAL_HOLDOUT=1
for n in 400 800 1600 3200; do
  half=$((n / 2))
  AIDA_N_TRAIN=$n ./venv/Scripts/python.exe eval_per_class_direct.py \
    --conditions clean clean_sub$half scale_m30 scale_m30_refined50 \
    --out ../backend/app/data/per_class_ak_n$n.csv
done
echo "=== 전부 완료 ==="
