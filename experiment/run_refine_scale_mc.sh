#!/bin/sh
# 규모 실험의 다중 클래스판 — X와 직접 비교하기 위한 것.
#
# run_refine_scale.sh는 Car 단일 클래스로 돈다(clean 0.879). X는 다중
# 클래스로 쟀으므로(clean 0.599) 두 수치를 직접 비교할 수 없다. 같은
# 클래스 구성으로 한 번 더 돌려야 X의 0.05배 / 0.34배와 이어붙일 수 있다.
#
# 나머지 설계는 단일 클래스판과 같다 — 중첩 부분집합, 고정 평가셋 800장.
# 그래서 X가 못 했던 것(프레임 구성 교란 제거)은 여기서도 유지된다.
#
# 다중 클래스는 학습이 더 느리다. 규모를 인자로 받으므로 시간이 부족하면
# 작은 것부터 돌릴 수 있다:
#
#   sh run_refine_scale_mc.sh            # 400 800 1600 3200 (약 8시간+)
#   sh run_refine_scale_mc.sh 400 800    # 두 점만 (약 2시간)
#
# 진행 상황은 refine_scale_mc.log에 쌓인다. 중간에 끊겨도 이미 학습한
# 조건은 건너뛰지 않으므로, 다시 돌리면 처음부터 간다는 점만 주의.
set -e
cd "$(dirname "$0")"

export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_FRAME_SELECT=nested
export AIDA_VAL_HOLDOUT=1
export AIDA_N_VAL=800
export AIDA_WORKERS=2

SCALES="${*:-400 800 1600 3200}"

for N in $SCALES; do
  export AIDA_N_TRAIN=$N
  HALF=$((N / 2))
  echo "########## [다중 클래스] N=$N (절반 $HALF) ##########"

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
  echo "########## [다중 클래스] N=$N 완료 ##########"
done

echo "=== 전부 완료 ==="
echo "결과 보기: AIDA_CLASSES=\"Car,Van,Pedestrian,Cyclist\" ./venv/Scripts/python.exe compare_refine_scale.py --mc"
