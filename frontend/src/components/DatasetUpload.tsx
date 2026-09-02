import { useEffect, useState } from "react";
import {
  diagnoseDataset,
  diagnoseDatasetLabels,
  getDatasetReportUrl,
  getReliabilityProfiles,
  uploadDataset,
} from "../api";
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

  useEffect(() => {
    // 프로파일을 못 불러와도 진단 자체는 기본값으로 돌아가야 하므로 조용히 넘긴다
    getReliabilityProfiles().then(setProfiles).catch(() => setProfiles([]));
  }, []);

  const busy = status === "uploading" || status === "diagnosing";
  const selectedProfile = profiles.find((p) => p.name === profile);

  const handleRun = async () => {
    if (!file) return;
    setStatus("uploading");
    setResult(null);
    setLabelResult(null);
    try {
      const info = await uploadDataset(file);
      setDataset(info);
      setStatus("diagnosing");
      // 박스 단위 진단이 실제 재검수 목록을 만드는 핵심이고, 데이터셋 단위
      // 진단은 성능 패턴 DB와의 비교 근거를 함께 보여주기 위해 같이 돌린다.
      const [labels, diagnosis] = await Promise.all([
        diagnoseDatasetLabels(info.dataset_id, profile),
        diagnoseDataset(info.dataset_id),
      ]);
      setLabelResult(labels);
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
        images/ + labels/(YOLO 포맷) 폴더를 담은 zip을 올리면, 이미 학습된
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

      {selectedProfile && selectedProfile.classes.length > 0 && (
        <p className="upload-meta">
          진단 클래스: {selectedProfile.classes.join(", ")}
          {selectedProfile.name
            ? " — 이 구성에서 실측한 유형 신뢰도를 적용합니다."
            : " — 기본 기준 모델입니다."}
        </p>
      )}

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
                  <th>의심 유형</th>
                  <th>건수</th>
                  <th>라벨 대비 비율</th>
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

          <h4 className="subsection-heading">우선 재검수 박스 (상위 20개)</h4>
          <div className="table-scroll">
            <table className="report-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>이미지</th>
                  <th>라벨</th>
                  <th>의심 유형</th>
                  <th>근거</th>
                </tr>
              </thead>
              <tbody>
                {labelResult.review_queue.slice(0, 20).map((item) => (
                  <tr key={`${item.image}-${item.label_index}-${item.rank}`}>
                    <td>{item.rank}</td>
                    <td>{item.image}</td>
                    <td>{item.label_index === null ? "—" : `#${item.label_index}`}</td>
                    <td>{item.label}</td>
                    <td>{item.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {labelResult.robustness.length > 0 && (
            <>
              <h3 className="subsection-heading">유형별 신뢰도 — 기준 모델이 맞지 않으면</h3>
              <p className="report-caveat">
                진단은 기준 모델의 예측을 자로 삼아 라벨을 잽니다. 그 모델이 이
                데이터와 다른 도메인에서 학습됐다면 유형마다 다르게 무너집니다.
                아래는 같은 데이터를 두 모델로 진단해 실측한 값입니다.
              </p>
              <div className="table-scroll">
                <table className="report-table">
                  <thead>
                    <tr>
                      <th>오류 유형</th>
                      <th>도메인 맞을 때</th>
                      <th>도메인 어긋날 때</th>
                      <th>판단</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...labelResult.robustness]
                      .sort((a, b) => b.shifted_domain - a.shifted_domain)
                      .map((r) => (
                        <tr key={r.suspicion}>
                          <td>{r.label}</td>
                          <td>{(r.matched_domain * 100).toFixed(1)}%</td>
                          <td>{(r.shifted_domain * 100).toFixed(1)}%</td>
                          <td className={r.robust ? "priority priority-높음" : "priority-rationale"}>
                            {r.robust ? "도메인 무관하게 신뢰" : "기준 모델에 의존"}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <p className="report-caveat">{labelResult.caveat}</p>
        </div>
      )}
    </section>
  );
}
