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
