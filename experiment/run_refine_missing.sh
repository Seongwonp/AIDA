#!/bin/sh
# `missing`에서의 자기 정제 (docs/22 계획 3번).
# AJ·AK는 scale_m30 하나로만 쟀다. missing은 도메인이 어긋나도 살아남는
# 유일한 유형이라(AI), 정제에서도 다르게 굴 수 있다.
#
# clean과 clean_subN은 오류 유형과 무관하므로 AK 것을 그대로 쓴다.
# 규모당 새로 학습하는 것은 missing_30과 missing_30_refined50 둘뿐이다.
set -e
cd "$(dirname "$0")"
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_FRAME_SELECT=nested
export AIDA_VAL_HOLDOUT=1
export AIDA_N_VAL=800
export AIDA_WORKERS=2

for N in ${*:-400 800}; do
  export AIDA_N_TRAIN=$N
  echo "########## missing N=$N ##########"
  ./venv/Scripts/python.exe train.py --condition missing_30
  ./venv/Scripts/python.exe refine_ruler.py --condition missing_30 --keep 0.5
  ./venv/Scripts/python.exe train.py --condition missing_30_refined50
  for c in missing_30 missing_30_refined50; do
    ./venv/Scripts/python.exe evaluate.py --condition "$c"
  done
  echo "########## missing N=$N 완료 ##########"
done
echo "=== 전부 완료 ==="
