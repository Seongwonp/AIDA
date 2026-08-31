set -e
cd "C:/Users/USER/Desktop/AIDA/experiment"
CONDS="scale_m30_asis scale_m30_fix_severity_25 scale_m30_fix_class_weighted_25 scale_m30_fix_random_25 scale_m30_fix_severity_50 scale_m30_fix_class_weighted_50 scale_m30_fix_random_50"
for seed in 43 44; do
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_WORKERS=2 \
  AIDA_TRAIN_SEED=$seed AIDA_RUN_SUFFIX="_s$seed" \
  ./venv/Scripts/python.exe run_all.py --skip-download --skip-preprocess --conditions $CONDS
done
