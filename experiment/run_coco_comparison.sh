#!/bin/sh
# COCO 조건을 두 자로 진단한다 — 진짜 도메인 이동 실험(docs/21 다음 할 일 5번).
#
#   COCO 자기(1C)    : COCO로 학습한 자           = 도메인 일치
#   KITTI→COCO(1C)   : KITTI로 학습한 자를 COCO에 = 진짜 도메인 이동
#
# Y~AH의 "도메인 이동"은 전부 KITTI 안에서의 프레임 선택 차이였다. 다른
# 데이터셋으로 넘어가도 "자가 데이터에 맞아야 진단이 산다"가 성립하는지 본다.
set -e
cd "$(dirname "$0")"

echo "학습 완료를 기다린다..."
while ! grep -q "=== 전부 완료 ===" train_coco.log 2>/dev/null; do sleep 20; done
echo "학습 완료 확인. 진단 시작."

AIDA_DATASET=coco ./venv/Scripts/python.exe compare_rulers_seeded.py \
  --limit 80 --all-conditions \
  --rulers coco_self kitti_on_coco \
  --seeds 42 123 2024 \
  --out seeded_coco_3seeds.json

echo "=== 비교 완료 ==="
