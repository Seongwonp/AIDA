#!/bin/sh
# AK의 남은 한계: "절반을 버리면 드문 클래스가 먼저 얇아진다"를 클래스별 mAP로
# 확인한다 (docs/22 계획 2번). 제품 문구에 "그렇게 보이지만 확인하지
# 않았습니다"라는 단서가 나가 있는데, 확인되면 뗄 수 있다.
#
# 학습하지 않는다. 저장된 best.pt로 검증셋만 다시 돈다.
set -e
cd "$(dirname "$0")"
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_FRAME_SELECT=nested
export AIDA_VAL_HOLDOUT=1
for n in 400 800 1600 3200; do
  half=$((n / 2))
  echo "########## N=$n ##########"
  AIDA_N_TRAIN=$n ./venv/Scripts/python.exe evaluate_per_class.py \
    --conditions clean clean_sub$half scale_m30 scale_m30_refined50
done
echo "=== 전부 완료 ==="
