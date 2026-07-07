import type { ErrorTypeReport } from "../types";

export function ErrorReportTable({ reports }: { reports: ErrorTypeReport[] }) {
  return (
    <section className="card">
      <h2>오류 유형 분석 · 재검수 우선순위</h2>
      <table className="report-table">
        <thead>
          <tr>
            <th>오류 유형</th>
            <th>최대 성능 저하</th>
            <th>재검수 우선순위</th>
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr key={r.error_type}>
              <td>{r.label}</td>
              <td>-{r.max_performance_drop_pct}%</td>
              <td>
                <span className={`priority priority-${r.review_priority}`}>
                  {r.review_priority}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
