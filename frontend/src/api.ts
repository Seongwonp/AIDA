import axios from "axios";
import type {
  ConditionMetric,
  ConditionMetricAgg,
  DatasetSummary,
  DiagnosisResult,
  LabelDiagnosisResult,
  DatasetHistoryItem,
  VerdictMap,
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

export const deleteDataset = (datasetId: string) =>
  client.delete(`/api/datasets/${datasetId}`).then(() => undefined);

export const getVerdicts = (datasetId: string) =>
  client
    .get<VerdictMap>(`/api/datasets/${datasetId}/verdicts`)
    .then((res) => res.data);

export const putVerdicts = (datasetId: string, verdicts: Record<string, string>) =>
  client
    .put<VerdictMap>(`/api/datasets/${datasetId}/verdicts`, { verdicts })
    .then((res) => res.data);

// ── 평가용 가림 판정 (docs/evaluation-adjudication-design.md) ────────────────
//
// **제품의 재검수 판정(`getVerdicts`/`putVerdicts`)과 다른 경로다.** 순위와
// 의심 유형을 보고 매긴 판정으로는 그 순위를 평가할 수 없어, 파일도 API도
// 나눠 둔다.

export type BlindQueueResponse = {
  evaluation_id: string;
  dataset_id: string;
  candidate_set_hash: string;
  candidates: Array<{
    canonical_candidate_id: string;
    image: string;
    label_index: number | null;
    box: number[] | null;
    class_name: string | null;
    verdict: "hit" | "miss" | "hold" | null;
    unique_error_id: string | null;
  }>;
  damaged: boolean;
};

export type AdjudicationRow = {
  canonical_candidate_id: string;
  verdict: "hit" | "miss" | "hold" | null;
  unique_error_id: string | null;
};

/** 평가를 시작한다 — 지금 후보 목록을 얼린다. 이미 있으면 409다. */
export const startEvaluation = (datasetId: string, evaluationId: string, shuffleSeed = 0) =>
  client
    .post(`/api/datasets/${datasetId}/evaluations`, {
      evaluation_id: evaluationId,
      shuffle_seed: shuffleSeed,
    })
    .then((res) => res.data);

export const getBlindQueue = (datasetId: string, evaluationId: string) =>
  client
    .get<BlindQueueResponse>(`/api/datasets/${datasetId}/evaluations/${evaluationId}/queue`)
    .then((res) => res.data);

// `candidateSetHash`를 함께 보낸다. 안 맞으면 서버가 저장하지 않는다 — 다른
// 목록에 붙은 판정을 되살리면 무엇을 가리키는지 알 수 없다.
export const putAdjudications = (
  datasetId: string,
  evaluationId: string,
  candidateSetHash: string,
  adjudications: AdjudicationRow[],
) =>
  client
    .put(`/api/datasets/${datasetId}/evaluations/${evaluationId}/adjudications`, {
      candidate_set_hash: candidateSetHash,
      adjudications,
    })
    .then((res) => res.data);

/**
 * 판정 작업 기록을 이어붙인다 (docs/pilot-evaluation-plan.md).
 *
 * **판정 저장(`putAdjudications`)과 별개의 경로다.** 판정은 지금의 사실이고
 * 기록은 지나간 사실이라, 한 파일에 두면 판정을 고칠 때마다 기록도 다시 써야
 * 한다.
 */
export const postActivity = (
  datasetId: string,
  evaluationId: string,
  candidateSetHash: string,
  events: unknown[],
) =>
  client
    .post(`/api/datasets/${datasetId}/evaluations/${evaluationId}/activity`, {
      candidate_set_hash: candidateSetHash,
      events,
    })
    .then((res) => res.data);

export type LabelBox = {
  label_index: number;
  class_id: number;
  class_name: string | null;
  /** cx, cy, w, h — 정규화(0~1). 화면이 이미지 크기로 픽셀로 바꾼다. */
  box: number[];
};

/**
 * 이미지 한 장에 이미 붙어 있는 라벨 전부.
 *
 * 가림 판정 화면이 문맥을 그리는 데 쓴다 — **주변이 안 보이면 판정할 수 없다.**
 * 의심 유형이나 점수는 담기지 않는다. 데이터셋의 사실이지 우리 판단이 아니다.
 */
export const getLabelBoxes = (datasetId: string, image: string) =>
  client
    .get<{ image: string; labels: LabelBox[] }>(
      `/api/datasets/${datasetId}/label-boxes/${encodeURIComponent(image)}`,
    )
    .then((res) => res.data);
