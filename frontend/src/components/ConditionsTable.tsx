import type { ConditionMetric } from "../types";

const TYPE_LABELS: Record<string, string> = {
  none: "기준선",
  width: "가로 오류",
  height: "세로 오류",
  rotation: "회전각 오류",
};

function formatMagnitude(condition: ConditionMetric) {
  if (condition.type === "none") return "0";
  const sign = condition.magnitude > 0 ? "+" : "";
  const unit = condition.type === "rotation" ? "°" : "%";
  return `${sign}${condition.magnitude}${unit}`;
}

function formatDrop(value: number) {
  if (value < 0) return `+${Math.abs(value).toFixed(1)}%`;
  return `-${value.toFixed(1)}%`;
}

function toCsvValue(value: string | number) {
  const text = String(value);
  return text.includes(",") || text.includes('"') || text.includes("\n")
    ? `"${text.replace(/"/g, '""')}"`
    : text;
}

function downloadConditionsCsv(conditions: ConditionMetric[]) {
  const headers = [
    "condition",
    "type",
    "magnitude",
    "map50",
    "map50_95",
    "precision",
    "recall",
    "performance_drop_pct",
  ];
  const rows = conditions.map((condition) =>
    headers.map((key) => toCsvValue(condition[key as keyof ConditionMetric])).join(","),
  );
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const link = document.createElement("a");
  link.href = url;
  link.download = `aida_conditions_${today}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function ConditionsTable({ conditions }: { conditions: ConditionMetric[] }) {
  return (
    <section className="card">
      <div className="card-heading-row">
        <h2>조건별 상세 지표</h2>
        <button
          className="refresh-button"
          type="button"
          onClick={() => downloadConditionsCsv(conditions)}
          disabled={conditions.length === 0}
        >
          CSV 다운로드
        </button>
      </div>

      <div className="table-scroll">
        <table className="report-table metrics-table">
          <thead>
            <tr>
              <th>조건</th>
              <th>유형</th>
              <th>강도</th>
              <th>mAP@0.5</th>
              <th>mAP@0.5:0.95</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>성능 변화</th>
            </tr>
          </thead>
          <tbody>
            {conditions.map((condition) => (
              <tr key={condition.condition}>
                <td>{condition.condition}</td>
                <td>{TYPE_LABELS[condition.type] ?? condition.type}</td>
                <td>{formatMagnitude(condition)}</td>
                <td>{condition.map50.toFixed(3)}</td>
                <td>{condition.map50_95.toFixed(3)}</td>
                <td>{condition.precision.toFixed(3)}</td>
                <td>{condition.recall.toFixed(3)}</td>
                <td>{formatDrop(condition.performance_drop_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
