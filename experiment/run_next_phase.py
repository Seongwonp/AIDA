import config
from train import train_condition
from evaluate import evaluate_condition, append_metrics
import generate_report
import pandas as pd
from pathlib import Path

if __name__ == "__main__":
    new_conditions = config.NEXT_PHASE_CONDITIONS
    print(f"Training {len(new_conditions)} new conditions...")
    
    metrics_path = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "metrics.csv"
    existing_conditions = set()
    if metrics_path.exists():
        try:
            metrics_df = pd.read_csv(metrics_path)
            existing_conditions = set(metrics_df["condition"].tolist())
        except Exception as e:
            print(f"Warning reading metrics.csv: {e}")

    for i, condition in enumerate(new_conditions, 1):
        if condition.name in existing_conditions:
            print(f"=== [{i}/{len(new_conditions)}] Skipping {condition.name} (already trained) ===")
            continue
            
        print(f"\n=== [{i}/{len(new_conditions)}] {condition.name} ===")
        try:
            train_condition(condition)
            row = evaluate_condition(condition)
            append_metrics(row)
        except Exception as e:
            print(f"Error processing {condition.name}: {e}")
    
    print("\nGenerating final report...")
    try:
        generate_report.main()
    except Exception as e:
        print(f"Error generating report: {e}")
        
    print("All next phase conditions trained, evaluated, and report generated!")
