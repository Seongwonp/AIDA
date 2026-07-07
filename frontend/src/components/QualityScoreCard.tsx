import type { DatasetSummary } from "../types";

export function QualityScoreCard({ summary }: { summary: DatasetSummary }) {
  return (
    <section className="card score-card">
      <div className="score-value">
        <span className="score-number">{summary.quality_score}</span>
        <span className="score-max">/100</span>
      </div>
      <div className="score-label">
        데이터셋 품질 점수
        <span className={`badge ${summary.certified ? "badge-certified" : "badge-pending"}`}>
          {summary.certified ? "CERTIFIED" : "검토 필요"}
        </span>
      </div>
      <div className="score-stats">
        <div>
          <strong>{summary.total_images.toLocaleString()}</strong>
          <span>총 이미지</span>
        </div>
        <div>
          <strong>{summary.total_objects.toLocaleString()}</strong>
          <span>총 객체</span>
        </div>
        <div>
          <strong>{summary.suspected_error_count.toLocaleString()}</strong>
          <span>오류 의심 건수</span>
        </div>
      </div>
    </section>
  );
}
