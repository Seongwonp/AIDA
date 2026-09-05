#!/bin/sh
# 클래스 구성이 같은 4클래스 자 세 대 (docs/22 계획 1번, AL이 남긴 구멍).
#
# 셋 다 broad 풀에서 뽑아 평가셋(cyclist_rich)과 겹침이 0이다. 다른 것은
# Cyclist를 몇 개나 봤느냐뿐 — 0개 / 39개 / 76개. 평가 데이터는 라벨의 20%가
# Cyclist라 이 차이가 진단 품질 차이로 이어질 것이고, 그래야 "적합도가 그
# 차이를 아는가"를 물을 수 있다.
#
# 시드 3개씩. AF에서 배운 것: n=3의 표준편차도 못 믿지만 n=1은 산포를 아예
# 말할 수 없다.
set -e
cd "$(dirname "$0")"
export AIDA_WORKERS=2
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_N_TRAIN=400
export AIDA_N_VAL=100

for sel in broad_poor broad_mid broad_rich; do
  export AIDA_FRAME_SELECT=$sel

  # 자에는 clean만 있으면 된다. 오류 조건은 평가 쪽(cyclist_rich)에 있다.
  echo "########## $sel 데이터 준비 ##########"
  ./venv/Scripts/python.exe data_loader.py
  ./venv/Scripts/python.exe -c "import config, error_injector; error_injector.build_condition(config._BY_NAME['clean'])"

  for ts in 42 123 2024; do
    if [ "$ts" = "42" ]; then suffix=""; else suffix="_ts$ts"; fi
    echo "########## $sel train_seed=$ts ##########"
    AIDA_TRAIN_SEED=$ts AIDA_RUN_SUFFIX=$suffix \
      ./venv/Scripts/python.exe train.py --condition clean
  done
done
echo "=== 전부 완료 ==="
