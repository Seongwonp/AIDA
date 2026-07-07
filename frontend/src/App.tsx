import { useEffect, useState } from "react";
import "./App.css";
import { getConditions, getDiagnosis, getSummary } from "./api";
import { ErrorReportTable } from "./components/ErrorReportTable";
import { PerformanceChart } from "./components/PerformanceChart";
import { QualityScoreCard } from "./components/QualityScoreCard";
import type { ConditionMetric, DatasetSummary, DiagnosisResult } from "./types";

function App() {
  const [summary, setSummary] = useState<DatasetSummary | null>(null);
  const [conditions, setConditions] = useState<ConditionMetric[]>([]);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getSummary(), getConditions(), getDiagnosis()])
      .then(([s, c, d]) => {
        setSummary(s);
        setConditions(c);
        setDiagnosis(d);
      })
      .catch(() => setError("백엔드(http://localhost:8000)에 연결할 수 없습니다."));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-kicker">AI 데이터 품질 인증 플랫폼</span>
        <h1>AIDA</h1>
      </header>

      {error && <p className="error-banner">{error}</p>}

      {summary && diagnosis && (
        <main className="app-grid">
          <QualityScoreCard summary={summary} />
          <PerformanceChart conditions={conditions} />
          <ErrorReportTable reports={diagnosis.error_reports} />
        </main>
      )}
    </div>
  );
}

export default App;
