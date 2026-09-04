import type { DatasetSummary } from "../types";

export function QualityScoreCard({ summary }: { summary: DatasetSummary }) {
  return (
    <section className="card score-card">
      {/* 사용자가 올린 데이터가 아니라 이 시스템을 보정한 KITTI 실험셋이다.
          제목에 '기준 실험'을 넣어두지 않으면 자기 점수로 읽힌다. */}
      <h2>기준 실험 데이터셋</h2>
      <div className="score-value">
        <span className="score-number">{summary.quality_score}</span>
        <span className="score-max">/100</span>
      </div>
      <div className="score-label">
        기준 실험 데이터셋 품질 점수
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
