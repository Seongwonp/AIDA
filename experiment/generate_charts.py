import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

def main():
    metrics_path = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "metrics.csv"
    if not metrics_path.exists():
        print("metrics.csv not found")
        return
    
    df = pd.read_csv(metrics_path)
    clean_row = df[df["condition"] == "clean"]
    if clean_row.empty:
        print("clean condition not found in metrics.csv")
        return
    
    baseline = clean_row["map50"].iloc[0]
    df = df[df["condition"] != "clean"].copy()
    df["drop_pct"] = (baseline - df["map50"]) / baseline * 100
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # We want a bar plot with a unique color for each type
    unique_types = df["type"].unique()
    # Define a custom color map for types
    colors_map = {
        "width": "#1f77b4",       # blue
        "height": "#aec7e8",      # light blue
        "rotation": "#ff7f0e",    # orange
        "translation_x": "#2ca02c",# green
        "translation_y": "#98df8a",# light green
        "scale": "#d62728"        # red
    }
    
    bar_colors = [colors_map.get(t, "#7f7f7f") for t in df["type"]]
    
    bars = ax.bar(
        df["condition"],
        df["drop_pct"],
        color=bar_colors,
        edgecolor="grey",
        width=0.6
    )
    
    # Grid
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    
    # Labels
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.yticks(fontsize=10)
    plt.xlabel("Error Condition", fontsize=12, fontweight="bold", labelpad=10)
    plt.ylabel("mAP@0.5 Drop Rate (%)", fontsize=12, fontweight="bold", labelpad=10)
    plt.title("AIDA Error Conditions: AI Model Performance Drop (mAP@0.5)", fontsize=14, fontweight="bold", pad=15)
    
    # Add a custom legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=colors_map.get(t, "#7f7f7f"), edgecolor="grey", label=t)
        for t in unique_types
    ]
    ax.legend(handles=legend_elements, title="Error Type", title_fontsize="11", loc="upper left")
    
    plt.tight_layout()
    
    out_dir = Path(__file__).resolve().parent.parent / "docs" / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "experiment-results-full21.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Chart saved successfully -> {out_path}")

if __name__ == "__main__":
    main()
