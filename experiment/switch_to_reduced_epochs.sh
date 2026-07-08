#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")"
LOG=run_priority1.log

echo "[switch] clean 조건 완료 대기 중..."
until grep -qE "\[clean\] metrics.csv 갱신|Traceback" "$LOG"; do
  sleep 5
done

if grep -q "Traceback" "$LOG"; then
  echo "[switch] clean 조건 학습 중 에러 발생, 중단"
  exit 1
fi

echo "[switch] clean 완료 확인, 기존 프로세스(50 epoch) 종료하고 나머지 6개 조건을 25 epoch로 재시작"
pkill -9 -f "run_all.py --priority 1" || true
sleep 3

source venv/bin/activate
for name in width_m30 width_p30 height_m30 height_p30 rot_m15 rot_p15; do
  echo "[switch] === $name (epochs=25) 학습 시작 ==="
  python train.py --condition "$name" --epochs 25 --evaluate
done

echo "[switch] 남은 6개 조건 전부 완료"
