import type { RoiEstimate } from "../types";

// RoiEstimate는 GET /api/roi-estimate 응답 그대로 — 계산은 전부 백엔드
// (backend/app/routers/report.py의 get_roi_estimate)에서 하고, 이 컴포넌트는
// 결과값을 원화·퍼센트로 포맷해서 보여주기만 한다.

function formatKrw(value: number) {
  return `${value.toLocaleString("ko-KR")}원`;
}

function formatRatio(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function RoiEstimateCard({ estimate }: { estimate: RoiEstimate }) {
  const { assumptions } = estimate;

  return (
    <section className="card roi-card">
      <div className="card-heading-row">
        <h2>ROI 정량화</h2>
        <span className="estimate-badge">{estimate.label}</span>
      </div>

      <div className="roi-summary">
        <div>
          <span>총 절감 추정</span>
          <strong>{formatKrw(estimate.total_savings_krw)}</strong>
        </div>
        <div>
          <span>재검수 범위 축소</span>
          <strong>{estimate.review_scope_reduction_pct.toFixed(1)}%</strong>
        </div>
      </div>

      <div className="roi-grid">
        <div>
          <span>수작업 검수 절감</span>
          <strong>{formatKrw(estimate.manual_review_savings_krw)}</strong>
          <small>
            전체 {assumptions.dataset_labels.toLocaleString("ko-KR")}건 중 의심{" "}
            {formatRatio(assumptions.suspected_review_ratio)}만 재검수
          </small>
        </div>
        <div>
          <span>GPU 재학습 절감</span>
          <strong>{formatKrw(estimate.gpu_savings_krw)}</strong>
          <small>
            재학습 {assumptions.gpu_retrain_runs_without_aida}회 →{" "}
            {assumptions.gpu_retrain_runs_with_aida}회 가정
          </small>
        </div>
      </div>

      <p className="report-caveat">
        계산식: 수작업 비용 = 라벨 수 × 건당 검수 시간 ÷ 60 × 시간당 인건비, GPU 비용 = 재학습 횟수 ×
        1회 비용. 실제 고객 단가가 아닌 발표용 가정값입니다.
      </p>
    </section>
  );
}
