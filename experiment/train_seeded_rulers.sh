#!/bin/sh
# 자를 진짜 다른 학습 시드로 만든다.
# 지금까지의 "3 시드" 자는 전부 오류 시드만 바꾼 것이라, clean 조건에는
# 주입할 오류가 없어 학습 데이터가 동일했다 — 시드 산포가 아니었다.
set -e
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_WORKERS=2
for sel in cyclist_rich random; do
  for ts in 123 2024; do
    echo "=== frame_select=$sel train_seed=$ts ==="
    if [ "$sel" = random ]; then unset AIDA_FRAME_SELECT; else export AIDA_FRAME_SELECT=$sel; fi
    AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=_ts$ts ./venv/Scripts/python.exe train.py --condition clean
  done
done
echo "=== 전부 완료 ==="
