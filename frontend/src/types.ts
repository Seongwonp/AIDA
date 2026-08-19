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
