import axios from "axios";
import type {
  ConditionMetric,
  ConditionMetricAgg,
  DatasetSummary,
  DiagnosisResult,
  LabelDiagnosisResult,
  ReliabilityProfile,
  RoiEstimate,
  UploadDiagnosisResult,
  UploadedDatasetInfo,
} from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const client = axios.create({
  baseURL: API_BASE_URL,
});

export const getSummary = () =>
  client.get<DatasetSummary>("/api/summary").then((res) => res.data);

export const getConditions = () =>
  client.get<ConditionMetric[]>("/api/conditions").then((res) => res.data);

export const getDiagnosis = () =>
  client.get<DiagnosisResult>("/api/diagnose").then((res) => res.data);

export const getRoiEstimate = () =>
  client.get<RoiEstimate>("/api/roi-estimate").then((res) => res.data);

export const getObbConditions = () =>
  client.get<ConditionMetric[]>("/api/obb/conditions").then((res) => res.data);

export const getAggregatedConditions = () =>
  client.get<ConditionMetricAgg[]>("/api/conditions/aggregated").then((res) => res.data);

export const getObbAggregatedConditions = () =>
  client.get<ConditionMetricAgg[]>("/api/obb/conditions/aggregated").then((res) => res.data);

export const uploadDataset = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return client
    .post<UploadedDatasetInfo>("/api/datasets/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((res) => res.data);
};

export const diagnoseDataset = (datasetId: string) =>
  client
    .post<UploadDiagnosisResult>(`/api/datasets/${datasetId}/diagnose`)
    .then((res) => res.data);

// profile은 유형 신뢰도 보정 프로파일 이름. 빈 값이면 기본값(KITTI Car 실측).
// 유형 신뢰도가 도메인을 타기 때문에 고를 수 있게 해둔 것이다 (docs/21 L).
export const diagnoseDatasetLabels = (datasetId: string, profile = "") =>
  client
    .post<LabelDiagnosisResult>(`/api/datasets/${datasetId}/diagnose-labels`, null, {
      params: profile ? { profile } : undefined,
    })
    .then((res) => res.data);

export const getReliabilityProfiles = () =>
  client
    .get<ReliabilityProfile[]>("/api/datasets/reliability-profiles")
    .then((res) => res.data);

export const getDatasetReportUrl = (datasetId: string) =>
  `${API_BASE_URL}/api/datasets/${datasetId}/report`;
