import { useEffect, useState } from "react";
import {
  diagnoseDataset,
  diagnoseDatasetLabels,
  getLabelDiagnosis,
  getDatasetReportUrl,
  getReliabilityProfiles,
  uploadDataset,
} from "../api";
import { ReviewQueue } from "./ReviewQueue";
import { HistoryCard } from "./HistoryCard";
import { RulerCard } from "./RulerCard";
import type {
  LabelDiagnosisResult,
  ReliabilityProfile,
  UploadDiagnosisResult,
  UploadedDatasetInfo,
} from "../types";

type Status = "idle" | "uploading" | "diagnosing" | "done" | "error";

export function DatasetUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [dataset, setDataset] = useState<UploadedDatasetInfo | null>(null);
  const [result, setResult] = useState<UploadDiagnosisResult | null>(null);
  const [labelResult, setLabelResult] = useState<LabelDiagnosisResult | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  // 유형 신뢰도는 도메인마다 다르다 — 다중 클래스로 재보니 "그 유형이 없을 때"의
  // 값이 크게 흔들렸다(docs/21 L). 그래서 보정 프로파일을 고를 수 있게 한다.
  const [profiles, setProfiles] = useState<ReliabilityProfile[]>([]);
  const [profile, setProfile] = useState("");
  // 추천에 따라 자동으로 바꿔 쓴 경우의 사유. 빈 문자열이면 안 바꿨다.
  const [autoProfile, setAutoProfile] = useState("");
  // 서버가 알려준 실패 사유. 없으면 일반 안내로 돌아간다.
  const [errorDetail, setErrorDetail] = useState("");

  useEffect(() => {
    // 프로파일을 못 불러와도 진단 자체는 기본값으로 돌아가야 하므로 조용히 넘긴다
    getReliabilityProfiles().then(setProfiles).catch(() => setProfiles([]));
  }, []);

  const busy = status === "uploading" || status === "diagnosing";
  const selectedProfile = profiles.find((p) => p.name === profile);

  /** 지난 진단을 그대로 불러온다. 추론을 다시 돌리지 않는다. */
  const openPast = async (datasetId: string) => {
    setStatus("diagnosing");
    setErrorDetail("");
    try {
      const labels = await getLabelDiagnosis(datasetId);
      setLabelResult(labels);
      setResult(null);          // 데이터셋 단위 결과는 따로 불러오지 않는다
      setDataset(null);
      setStatus("done");
      // 결과가 화면 아래에 붙으므로 거기로 데려간다
      requestAnimationFrame(() =>
        document.querySelector(".upload-card")?.scrollIntoView({ block: "start" }));
    } catch {
      setErrorDetail("지난 진단을 불러오지 못했습니다.");
      setStatus("error");
    }
  };

  const handleRun = async () => {
    if (!file) return;
    setStatus("uploading");
    setErrorDetail("");
    setResult(null);
    setLabelResult(null);
    try {
      const info = await uploadDataset(file);
      setDataset(info);
      // 자가 모르는 클래스는 오탐도 아니고 아예 검사되지 않는다 — 화면에
      // 흔적이 없어 "문제 없음"과 구별이 안 된다. 사용자가 직접 고르지 않은
      // 경우에만 추천을 따르고, 무엇을 왜 바꿨는지 표시한다. 명시적으로 고른
      // 프로파일은 건드리지 않는다.
      const used = profile || info.suggested_profile || "";
      setAutoProfile(!profile && info.suggested_profile ? info.suggestion_reason : "");
      setStatus("diagnosing");
      // 박스 단위 진단이 실제 재검수 목록을 만드는 핵심이고, 데이터셋 단위
      // 진단은 성능 패턴 DB와의 비교 근거를 함께 보여주기 위해 같이 돌린다.
      const [labels, diagnosis] = await Promise.all([
        diagnoseDatasetLabels(info.dataset_id, used),
        diagnoseDataset(info.dataset_id),
      ]);
      setLabelResult(labels);
      setResult(diagnosis);
      setStatus("done");
    } catch (e) {
      // FastAPI는 400/422에 detail을 담아 준다. axios는 그걸 response.data에
      // 넣어두는데, 지금까지는 통째로 버리고 있었다.
      const detail = (e as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      setErrorDetail(typeof detail === "string" ? detail : "");
      setStatus("error");
    }
  };

  return (
    <section className="card upload-card">
      <div className="card-heading-row">
        <h2>내 데이터셋 진단</h2>
        <span className="badge badge-pending">베타</span>
      </div>
      <p className="report-caveat">
        images/ + labels/(YOLO 포맷) 폴더를 담은 zip을 올리면 — 폴더째
        우클릭해 압축한 것도 그대로 됩니다 — 이미 학습된
        기준 모델로 추론해 어떤 오류 유형과 가장 비슷한지 후보를 보여줍니다.
        아래에서 고른 클래스 구성과 같은 라벨이어야 합니다. 이 데이터셋이
        기준 모델의 데이터와 비슷한 난이도라고 가정하는 확률적 추정이며,
        확정 진단이 아닙니다.
      </p>

      <div className="upload-controls">
        <label htmlFor="dataset-zip-input" className="sr-only">
          진단할 데이터셋 zip 파일 선택
        </label>
        <input
          id="dataset-zip-input"
          type="file"
          accept=".zip"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={busy}
        />
        {profiles.length > 1 && (
          <>
            <label htmlFor="reliability-profile-select" className="sr-only">
              유형 신뢰도 보정 프로파일
            </label>
            <select
              id="reliability-profile-select"
              className="profile-select"
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              disabled={busy}
            >
              {profiles.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.available}>
                  {p.label}
                  {p.available ? "" : " — 기준 모델 없음"}
                </option>
              ))}
            </select>
          </>
        )}
        <button className="refresh-button" onClick={handleRun} disabled={!file || busy}>
          {status === "uploading" ? "업로드 중..." : status === "diagnosing" ? "진단 중..." : "업로드 & 진단"}
        </button>
      </div>

      {/* 자동 전환이 일어났으면 이 줄은 거짓이 된다 — 고른 것과 실제로
          쓴 것이 다르기 때문이다. 그때는 아래 전환 안내가 대신한다. */}
      {!autoProfile && selectedProfile && selectedProfile.classes.length > 0 && (
        <p className="upload-meta">
          진단 클래스: {selectedProfile.classes.join(", ")}
          {selectedProfile.name
            ? " — 이 구성에서 실측한 유형 신뢰도를 적용합니다."
            : " — 기본 기준 모델입니다."}
        </p>
      )}

      {autoProfile && (
        <p className="upload-meta">
          기준 모델을 자동으로 바꿔 진단했습니다 — {autoProfile}
        </p>
      )}

      {busy && (
        <div className="run-status" role="status" aria-live="polite">
          <span className="run-spinner" aria-hidden="true" />
          <div>
            <strong>
              {status === "uploading" ? "zip을 올리고 여는 중" : "기준 모델로 추론하는 중"}
            </strong>
            <span className="run-status-note">
              {status === "uploading"
                ? "이미지와 라벨 개수를 확인합니다."
                : "이미지마다 예측을 내고 라벨과 박스 단위로 대조합니다. 장수에 따라 수십 초 걸릴 수 있습니다."}
            </span>
          </div>
        </div>
      )}

      {status === "idle" && <HistoryCard onOpen={openPast} />}

      {status === "error" && (
        <div className="error-banner">
          <strong>업로드 또는 진단에 실패했습니다.</strong>
          {errorDetail ? (
            <p className="error-detail">{errorDetail}</p>
          ) : (
            <p className="error-detail">
              zip 구조(images/, labels/)를 확인하거나, 백엔드가 떠 있는지 보고
              잠시 후 다시 시도하세요.
            </p>
          )}
        </div>
      )}

      {dataset && (
        <p className="upload-meta">
          이미지 {dataset.num_images.toLocaleString()}장 · 라벨{" "}
          {dataset.num_labels.toLocaleString()}개 업로드됨 (dataset_id:{" "}
          {dataset.dataset_id})
        </p>
      )}

      {result && (
        <div className="upload-result">
          <div className="card-heading-row">
            <div className="score-value">
              <span className="score-number">{result.quality_score}</span>
              <span className="score-max">/100</span>
            </div>
            <a
              className="refresh-button"
              href={getDatasetReportUrl(result.dataset_id)}
              download={`aida_report_${result.dataset_id}.html`}
            >
              리포트 다운로드
            </a>
          </div>
          <div className="score-stats">
            <div>
              <strong>{result.performance_vector.map50.toFixed(3)}</strong>
              <span>mAP@0.5</span>
            </div>
            <div>
              <strong>{result.performance_vector.precision.toFixed(3)}</strong>
              <span>Precision</span>
            </div>
            <div>
              <strong>{result.performance_vector.recall.toFixed(3)}</strong>
              <span>Recall</span>
            </div>
          </div>

          <div className="table-scroll">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">의심 오류 유형</th>
                  <th scope="col">가장 가까운 조건</th>
                  <th scope="col">거리(가까울수록 유력)</th>
                </tr>
              </thead>
              <tbody>
                {result.candidates.map((c) => (
                  <tr key={c.error_type}>
                    <td>{c.label}</td>
                    <td>
                      {c.closest_condition} ({c.closest_magnitude > 0 ? "+" : ""}
                      {c.closest_magnitude})
                    </td>
                    <td>{c.distance.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="report-caveat">{result.caveat}</p>
        </div>
      )}

      {labelResult && (
        <div className="upload-result">
          <h3 className="subsection-heading">재검수 우선순위</h3>

          <p className="verdict">
            {labelResult.systematic ? (
              <>
                라벨 {labelResult.total_labels.toLocaleString()}개 중{" "}
                <strong>{labelResult.total_findings.toLocaleString()}개</strong>가 의심되며,
                그중 <strong>{labelResult.dominant_label}</strong>이(가){" "}
                {(labelResult.dominant_ratio * 100).toFixed(1)}%로 몰려 있어{" "}
                <strong>계통적 라벨 오류로 판단</strong>됩니다.
              </>
            ) : (
              <>
                라벨 {labelResult.total_labels.toLocaleString()}개 중{" "}
                {labelResult.total_findings.toLocaleString()}개가 의심되지만 특정 유형에
                몰리지 않아, <strong>계통적 오류로 보기는 어렵습니다</strong>. (모델 예측
                자체의 흔들림일 가능성)
              </>
            )}
          </p>

          <div className="table-scroll">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">의심 유형</th>
                  <th scope="col">건수</th>
                  <th scope="col">라벨 대비 비율</th>
                </tr>
              </thead>
              <tbody>
                {labelResult.by_type.map((t) => (
                  <tr key={t.suspicion}>
                    <td>{t.label}</td>
                    <td>{t.count.toLocaleString()}</td>
                    <td>{(t.ratio * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h4 className="subsection-heading">우선 재검수 박스</h4>
          <ReviewQueue items={labelResult.review_queue}
                       datasetId={labelResult.dataset_id} />

          <RulerCard result={labelResult} />

          <p className="report-caveat">{labelResult.caveat}</p>
        </div>
      )}
    </section>
  );
}
