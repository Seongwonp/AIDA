import axios from "axios";
import type { ConditionMetric, DatasetSummary, DiagnosisResult, RoiEstimate } from "./types";

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
