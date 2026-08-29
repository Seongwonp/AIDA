import { useState } from "react";
import { diagnoseDataset, getDatasetReportUrl, uploadDataset } from "../api";
import type { UploadDiagnosisResult, UploadedDatasetInfo } from "../types";

type Status = "idle" | "uploading" | "diagnosing" | "done" | "error";

export function DatasetUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [dataset, setDataset] = useState<UploadedDatasetInfo | null>(null);
  const [result, setResult] = useState<UploadDiagnosisResult | null>(null);
  const [status, setStatus] = useState<Status>("idle");

  const busy = status === "uploading" || status === "diagnosing";

  const handleRun = async () => {
    if (!file) return;
    setStatus("uploading");
    setResult(null);
    try {
      const info = await uploadDataset(file);
      setDataset(info);
      setStatus("diagnosing");
      const diagnosis = await diagnoseDataset(info.dataset_id);
      setResult(diagnosis);
      setStatus("done");
    } catch {
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
        images/ + labels/(YOLO 포맷, 클래스 1개) 폴더를 담은 zip을 올리면, 이미
        학습된 기준 모델로 추론해 어떤 오류 유형과 가장 비슷한지 후보를
        보여줍니다. 이 데이터셋이 KITTI Car와 비슷한 난이도라고 가정하는
        확률적 추정이며, 확정 진단이 아닙니다.
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
        <button className="refresh-button" onClick={handleRun} disabled={!file || busy}>
          {status === "uploading" ? "업로드 중..." : status === "diagnosing" ? "진단 중..." : "업로드 & 진단"}
        </button>
      </div>

      {status === "error" && (
        <p className="error-banner">
          업로드 또는 진단 중 오류가 발생했습니다. zip 구조(images/, labels/)를
          확인하거나 잠시 후 다시 시도하세요.
        </p>
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
                  <th>의심 오류 유형</th>
                  <th>가장 가까운 조건</th>
                  <th>거리(가까울수록 유력)</th>
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
    </section>
  );
}
