import axios from "axios";
import type {
  ConditionMetric,
  ConditionMetricAgg,
  DatasetSummary,
  DiagnosisResult,
  LabelDiagnosisResult,
  DatasetHistoryItem,
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

// profileClasses는 어느 클래스 구성의 성능 패턴 DB를 볼지 정한다. 비우면
// 기본(KITTI Car 단일). 같은 라벨 오류라도 클래스 구성에 따라 저하가 크게
// 다르므로 DB 자체가 갈린다 (docs/21 Q).
const classParams = (profileClasses: string) =>
  profileClasses ? { params: { profile_classes: profileClasses } } : undefined;

export const getConditions = (profileClasses = "") =>
  client
    .get<ConditionMetric[]>("/api/conditions", classParams(profileClasses))
    .then((res) => res.data);

export const getDiagnosis = (profileClasses = "") =>
  client
    .get<DiagnosisResult>("/api/diagnose", classParams(profileClasses))
    .then((res) => res.data);

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

export const getDatasetHistory = () =>
  client
    .get<DatasetHistoryItem[]>("/api/datasets/history")
    .then((res) => res.data);

/** 지난 진단을 다시 읽는다. 추론을 돌리지 않는다. */
export const getLabelDiagnosis = (datasetId: string) =>
  client
    .get<LabelDiagnosisResult>(`/api/datasets/${datasetId}/label-diagnosis`)
    .then((res) => res.data);
