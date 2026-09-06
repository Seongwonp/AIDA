#!/bin/sh
# 정제 비율을 바꾼다 (docs/23 계획 1번).
#
# 대조군도 비율마다 새로 만든다 — AK·AQ의 clean_sub{N/2}는 절반을 버린 것이라
# keep 0.5에만 맞는다. 70%를 남겼으면 70%짜리 clean 대조군과 견줘야 공정하다.
set -e
cd "$(dirname "$0")"
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_FRAME_SELECT=nested
export AIDA_VAL_HOLDOUT=1
export AIDA_N_VAL=800
export AIDA_WORKERS=2

for N in ${*:-400 800}; do
  export AIDA_N_TRAIN=$N
  for K in 30 70; do
    SUB=$((N * K / 100))
    echo "########## N=$N keep=${K}% (대조군 clean_sub$SUB) ##########"
    ./venv/Scripts/python.exe refine_ruler.py --condition missing_30 --keep 0.$K
    ./venv/Scripts/python.exe build_clean_subset.py --from missing_30_refined$K
    ./venv/Scripts/python.exe train.py --condition missing_30_refined$K
    ./venv/Scripts/python.exe train.py --condition clean_sub$SUB
    ./venv/Scripts/python.exe evaluate.py --condition missing_30_refined$K
    ./venv/Scripts/python.exe evaluate.py --condition clean_sub$SUB
  done
done
echo "=== 전부 완료 ==="
