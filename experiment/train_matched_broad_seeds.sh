#!/bin/sh
# 자기 도메인·넓은 자도 7시드로 맞춘다.
#
# AF에서 배운 것: n=3의 표준편차는 그 자체가 못 믿을 값이다. 먼 이동 자가
# ±0.46 → ±2.50으로 5배 넓어졌고 그 바람에 AD의 결론 하나가 무너졌다.
# 네 자를 같은 n으로 놓지 않으면 이번에도 같은 실수를 반복하게 된다.
set -e
export AIDA_WORKERS=2
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
for ts in 7 777 2025 31337; do
  echo "=== 자기 도메인(cyclist_rich) train_seed=$ts ==="
  AIDA_FRAME_SELECT=cyclist_rich \
    AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean

  echo "=== 넓은 자(broad 800장) train_seed=$ts ==="
  AIDA_FRAME_SELECT=broad AIDA_N_TRAIN=800 AIDA_N_VAL=200 \
    AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean
done
echo "=== 전부 완료 ==="
