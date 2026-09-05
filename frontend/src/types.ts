export interface DatasetSummary {
  total_images: number;
  total_objects: number;
  suspected_error_count: number;
  quality_score: number;
  certified: boolean;
}

export interface ConditionMetric {
  condition: string;
  type: string;
  magnitude: number;
  map50: number;
  map50_95: number;
  precision: number;
  recall: number;
  performance_drop_pct: number;
  mean_iou: number | null;
  mean_iou_drop_pct: number | null;
}

export interface ErrorTypeReport {
  error_type: string;
  label: string;
  max_performance_drop_pct: number;
  review_priority: string;
  priority_rationale: string;
}

export interface DiagnosisResult {
  dataset_name: string;
  quality_score: number;
  certified: boolean;
  generated_at: string;
  error_reports: ErrorTypeReport[];
}

export interface ConditionMetricAgg {
  condition: string;
  type: string;
  magnitude: number;
  n_seeds: number;
  map50_mean: number;
  map50_std: number;
  map50_95_mean: number;
  map50_95_std: number;
  precision_mean: number;
  precision_std: number;
  recall_mean: number;
  recall_std: number;
  drop_pct_mean: number | null;
  drop_pct_std: number | null;
}

export interface UploadedDatasetInfo {
  dataset_id: string;
  uploaded_at: string;
  num_images: number;
  num_labels: number;
  /** 라벨에 실제로 등장하는 클래스 인덱스 */
  label_class_ids: number[];
  /** 이 데이터에 맞는 기준 모델. null이면 기본값으로 충분하다는 뜻. */
  suggested_profile: string | null;
  suggestion_reason: string;
}

export interface PerformanceVector {
  map50: number;
  map50_95: number;
  precision: number;
  recall: number;
}

export interface ErrorTypeCandidate {
  error_type: string;
  label: string;
  closest_condition: string;
  closest_magnitude: number;
  distance: number;
}

export interface UploadDiagnosisResult {
  dataset_id: string;
  generated_at: string;
  performance_vector: PerformanceVector;
  quality_score: number;
  candidates: ErrorTypeCandidate[];
  caveat: string;
}

export interface SuspicionTypeCount {
  suspicion: string;
  label: string;
  count: number;
  ratio: number;
}

export interface ReviewQueueItem {
  rank: number;
  image: string;
  label_index: number | null;
  suspicion: string;
  label: string;
  severity: number;
  detail: string;
  /** 픽셀 좌표 [x1, y1, x2, y2]. 이 기능 전 진단 결과에는 없다. */
  box: number[] | null;
}

export interface LabelDiagnosisResult {
  dataset_id: string;
  generated_at: string;
  total_labels: number;
  total_findings: number;
  suspicion_ratio: number;
  dominant_type: string | null;
  dominant_label: string | null;
  dominant_ratio: number;
  systematic: boolean;
  by_type: SuspicionTypeCount[];
  review_queue: ReviewQueueItem[];
  robustness: TypeRobustness[];
  ruler: RulerInfo | null;
  caveat: string;
}

/**
 * 이 진단에 자로 쓴 기준 모델 (docs/21 AA·AD).
 * AA와 AD가 같은 말을 한다: 대상 분포에서의 실력이 전부다. 학습량도 클래스
 * 폭도 그 자체로는 진단 품질을 정하지 않는다. 그래서 어느 자를 썼는지가
 * 결과를 읽는 데 필요한 정보다.
 */
export interface RulerInfo {
  profile: string;
  profile_label: string;
  classes: string[];
  weights: string;
  class_aware: boolean;
  /** 학습 시드만 바꿔 같은 자를 만들었을 때 상위 10% 정밀도의 표준편차(%p) */
  seed_spread_pp: number;
  /** 업로드된 라벨에 이 자가 모르는 클래스 인덱스 */
  unknown_class_ids: number[];
}

/**
 * 이 오류 유형이 기준 모델의 상태에 얼마나 좌우되는가 (docs/21 V·Y 실측).
 * 진단은 기준 모델의 예측을 자로 삼는데, 판정에 따라 그 자를 쓰는 방식이
 * 달라서 도메인이 어긋났을 때 유형마다 다르게 무너진다.
 */
export interface TypeRobustness {
  suspicion: string;
  label: string;
  matched_domain: number;
  shifted_domain: number;
  robust: boolean;
  /**
   * 아예 다른 데이터셋에서 잰 값 (docs/21 AI). shifted_domain은 같은 KITTI
   * 안에서 프레임 구성만 바꿔 잰 것이라 낙관적이다.
   */
  cross_dataset: number | null;
}

export interface RoiAssumptions {
  dataset_labels: number;
  manual_review_minutes_per_label: number;
  reviewer_hourly_cost_krw: number;
  suspected_review_ratio: number;
  gpu_retrain_runs_without_aida: number;
  gpu_retrain_runs_with_aida: number;
  gpu_cost_per_run_krw: number;
}

export interface RoiEstimate {
  label: string;
  assumptions: RoiAssumptions;
  manual_review_cost_without_aida_krw: number;
  manual_review_cost_with_aida_krw: number;
  manual_review_savings_krw: number;
  gpu_cost_without_aida_krw: number;
  gpu_cost_with_aida_krw: number;
  gpu_savings_krw: number;
  total_savings_krw: number;
  review_scope_reduction_pct: number;
}


/** 유형 신뢰도 보정 프로파일. name이 빈 문자열이면 기본값(KITTI Car 실측). */
export interface ReliabilityProfile {
  name: string;
  label: string;
  types: string[];
  /** 이 상수를 잰 클래스 구성. 진단도 같은 구성으로 돌아간다. */
  classes: string[];
  /** 이 구성의 기준 모델이 서버에 있는가. false면 고를 수 없다. */
  available: boolean;
}
