import type { ConditionMetric } from "../types";

// backend/app/routers/report.py의 TYPE_LABELS, PerformanceChart.tsx와 목록을 맞춰야 함
// (한 곳에만 새 오류 유형을 추가하면 다른 화면엔 영어 타입명이 그대로 노출됨)
const TYPE_LABELS: Record<string, string> = {
  none: "기준선",
  width: "가로 오류",
  height: "세로 오류",
  rotation: "회전각 오류",
  translation_x: "가로이동 오류",
  translation_y: "세로이동 오류",
  scale: "스케일 오류",
  missing: "라벨 누락",
  duplicate: "라벨 중복",
  class_swap: "클래스 오기입",
};

// magnitude는 오류 유형에 따라 단위가 다르다: 회전각만 도(°), 나머지는 전부 %
function formatMagnitude(condition: ConditionMetric) {
  if (condition.type === "none") return "0";
  const sign = condition.magnitude > 0 ? "+" : "";
  const unit = condition.type === "rotation" ? "°" : "%";
  return `${sign}${condition.magnitude}${unit}`;
}

// performance_drop_pct는 "clean 대비 저하율"이라 음수면 오히려 clean보다 좋아졌다는 뜻
// (단일 시드 학습이라 발생하는 노이즈일 수 있음, docs/12-experiment-results.md 참고)
function formatDrop(value: number) {
  if (value < 0) return `+${Math.abs(value).toFixed(1)}%`;
  return `-${value.toFixed(1)}%`;
}

function formatOptionalNumber(value: number | null, digits: number) {
  return value === null ? "-" : value.toFixed(digits);
}

function formatOptionalDrop(value: number | null) {
  return value === null ? "-" : `-${value.toFixed(2)}%`;
}

// 쉼표·따옴표·줄바꿈이 든 값은 CSV 규격에 맞게 큰따옴표로 감싸야 엑셀에서 깨지지 않음
function toCsvValue(value: string | number | null) {
  const text = value === null ? "" : String(value);
  return text.includes(",") || text.includes('"') || text.includes("\n")
    ? `"${text.replace(/"/g, '""')}"`
    : text;
}

// 서버 호출 없이 이미 받아온 조건별 데이터를 그대로 CSV로 변환해 다운로드시킨다
// (백엔드에 별도 export 엔드포인트가 없어도 되는 구조, docs/14-dashboard-enhancement-plan.md 참고)
function downloadConditionsCsv(conditions: ConditionMetric[]) {
  const headers = [
    "condition",
    "type",
    "magnitude",
    "map50",
    "map50_95",
    "precision",
    "recall",
    "mean_iou",
    "mean_iou_drop_pct",
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
              <th>평균 IoU</th>
              <th>IoU 감소율</th>
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
                <td>{formatOptionalNumber(condition.mean_iou, 4)}</td>
                <td>{formatOptionalDrop(condition.mean_iou_drop_pct)}</td>
                <td>{formatDrop(condition.performance_drop_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
