#!/bin/sh
# AD에서 먼 이동 자(Car 1클래스)의 표준편차가 ±0.46으로 나머지(±2.3~4.8)의
# 5분의 1이었다. 다만 세 값이 65.4 / 64.6 / 65.4로 우연히 가까울 수 있다.
# 시드를 7개로 늘려 이게 진짜인지 본다.
#
# 비교 대상인 약한 이동 자(4클래스)도 같은 시드 수로 맞춘다 — n이 다르면
# 표준편차끼리 비교할 수 없다.
set -e
export AIDA_WORKERS=2
for ts in 7 777 2025 31337; do
  echo "=== 먼 이동(Car 1클래스) train_seed=$ts ==="
  AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean

  echo "=== 약한 이동(4클래스) train_seed=$ts ==="
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" \
    AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean
done
echo "=== 전부 완료 ==="
