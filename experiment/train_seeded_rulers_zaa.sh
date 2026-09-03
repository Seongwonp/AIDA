#!/bin/sh
# Z의 먼 이동 자(Car 1클래스)와 AA의 넓은 자(broad 800장)에 학습 시드를 붙인다.
# AC와 같은 방식: clean 데이터는 시드와 무관하므로 조건 폴더는 그대로 쓰고
# 실행 폴더 이름에만 시드를 붙인다(clean_ts123).
set -e
export AIDA_WORKERS=2
for ts in 123 2024; do
  echo "=== 먼 이동(Car 1클래스) train_seed=$ts ==="
  AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean

  echo "=== 넓은 자(broad 4클래스 800장) train_seed=$ts ==="
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_FRAME_SELECT=broad \
    AIDA_N_TRAIN=800 AIDA_N_VAL=200 \
    AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean
done
echo "=== 전부 완료 ==="
