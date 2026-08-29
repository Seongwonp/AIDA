import type { ErrorTypeReport } from "../types";

export function ErrorReportTable({ reports }: { reports: ErrorTypeReport[] }) {
  return (
    <section className="card">
      <h2>오류 유형 확률 진단 · 재검수 우선순위 가이드</h2>
      <p className="report-caveat">
        성능 저하 패턴을 기준으로 어떤 오류 유형이 있을 가능성이 높은지 추정한
        결과입니다. 라벨 오류를 100% 확정하는 것이 아니라, 재검수 자원을
        우선 투입할 영역을 좁혀주는 가이드로 활용하세요.
      </p>
      <table className="report-table">
        <thead>
          <tr>
            <th>오류 유형</th>
            <th>최대 성능 저하</th>
            <th>재검수 우선순위</th>
            <th>판단 근거</th>
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
              <td className="priority-rationale">{r.priority_rationale}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
