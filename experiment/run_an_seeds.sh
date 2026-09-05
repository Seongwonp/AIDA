#!/bin/sh
# AN 처방에 시드를 붙인다 (docs/22 계획 1번).
# 지금은 시드 42 하나다. 이 프로젝트는 시드 때문에 결론이 세 번 뒤집혔다
# (AD→AF, X→AJ, AJ의 3점→4점).
set -e
cd "$(dirname "$0")"
export AIDA_CLASSES="Car,Van,Pedestrian,Cyclist"
export AIDA_FRAME_SELECT=cyclist_rich
for s in 123 2024; do
  echo "########## seed $s ##########"
  ./venv/Scripts/python.exe rank_systematic_first.py --seed $s --out rank_fix_seed$s.json
done
echo "=== 전부 완료 ==="
