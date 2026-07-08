import { useEffect, useState } from "react";
import "./App.css";
import { getConditions, getDiagnosis, getRoiEstimate, getSummary } from "./api";
import { ConditionsTable } from "./components/ConditionsTable";
import { ErrorReportTable } from "./components/ErrorReportTable";
import { PerformanceChart } from "./components/PerformanceChart";
import { QualityScoreCard } from "./components/QualityScoreCard";
import { RoiEstimateCard } from "./components/RoiEstimateCard";
import type { ConditionMetric, DatasetSummary, DiagnosisResult, RoiEstimate } from "./types";

function App() {
  const [summary, setSummary] = useState<DatasetSummary | null>(null);
  const [conditions, setConditions] = useState<ConditionMetric[]>([]);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [roiEstimate, setRoiEstimate] = useState<RoiEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([getSummary(), getConditions(), getDiagnosis(), getRoiEstimate()])
      .then(([s, c, d, r]) => {
        setSummary(s);
        setConditions(c);
        setDiagnosis(d);
        setRoiEstimate(r);
      })
      .catch(() => setError("백엔드(http://localhost:8000)에 연결할 수 없습니다."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-kicker">AI 데이터 품질 인증 플랫폼</span>
        <h1>AIDA</h1>
        <button className="refresh-button" onClick={load} disabled={loading}>
          {loading ? "불러오는 중..." : "새로고침"}
        </button>
      </header>

      {error && <p className="error-banner">{error}</p>}

      {loading && !summary && <p className="loading-banner">데이터를 불러오는 중입니다...</p>}

      {summary && diagnosis && roiEstimate && (
        <main className="app-grid">
          <QualityScoreCard summary={summary} />
          <RoiEstimateCard estimate={roiEstimate} />
          <PerformanceChart conditions={conditions} />
          <ConditionsTable conditions={conditions} />
          <ErrorReportTable reports={diagnosis.error_reports} />
        </main>
      )}
    </div>
  );
}

export default App;

