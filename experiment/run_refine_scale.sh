#!/bin/sh
# 자기 정제의 손익을 규모별로 분해한다 (docs/21 W·X의 재시험, 다음 할 일 4번).
#
# 규모마다 네 칸을 학습한다:
#   clean                 전체 N장 · 오류 0%    상한
#   scale_m30             전체 N장 · 오류 30%   정제 안 함
#   clean_sub<N/2>        절반    · 오류 0%     데이터 손해만 분리한 대조군
#   scale_m30_refined50   절반    · 오류 ~12%   정제한 것
#
# X는 400장과 800장 두 점만 봤고, 그 둘은 **프레임 구성도 달랐다**. 여기서는
# 한 순열에서 앞부터 잘라 쓰므로 작은 규모가 큰 규모의 부분집합이고
# (--select nested), 평가셋은 목록 끝 800장으로 고정된다(AIDA_VAL_HOLDOUT=1).
# 그래서 네 점이 서로 비교 가능하다.
set -e
cd "$(dirname "$0")"

export AIDA_FRAME_SELECT=nested
export AIDA_VAL_HOLDOUT=1
export AIDA_N_VAL=800
export AIDA_WORKERS=2

for N in 400 800 1600 3200; do
  export AIDA_N_TRAIN=$N
  HALF=$((N / 2))
  echo "########## N=$N (절반 $HALF) ##########"

  echo "--- 데이터 준비 ---"
  ./venv/Scripts/python.exe data_loader.py
  ./venv/Scripts/python.exe error_injector.py

  echo "--- clean, scale_m30 학습 ---"
  ./venv/Scripts/python.exe train.py --condition clean
  ./venv/Scripts/python.exe train.py --condition scale_m30

  # 정제는 self 자가 필요하다 — scale_m30을 학습한 뒤라야 돌릴 수 있다.
  echo "--- 정제 부분집합 생성 ---"
  ./venv/Scripts/python.exe refine_ruler.py --condition scale_m30 --keep 0.5
  ./venv/Scripts/python.exe build_clean_subset.py --from scale_m30_refined50

  echo "--- 대조군 학습 ---"
  ./venv/Scripts/python.exe train.py --condition "clean_sub$HALF"
  ./venv/Scripts/python.exe train.py --condition scale_m30_refined50

  echo "--- 평가 ---"
  for c in clean scale_m30 "clean_sub$HALF" scale_m30_refined50; do
    ./venv/Scripts/python.exe evaluate.py --condition "$c"
  done
  echo "########## N=$N 완료 ##########"
done

echo "=== 전부 완료 ==="
