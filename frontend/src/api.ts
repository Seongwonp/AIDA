import axios from "axios";
import type {
  ConditionMetric,
  ConditionMetricAgg,
  DatasetSummary,
  DiagnosisResult,
  RoiEstimate,
  UploadDiagnosisResult,
  UploadedDatasetInfo,
} from "./types";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
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
