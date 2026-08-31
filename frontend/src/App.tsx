import { useEffect, useState } from "react";
import "./App.css";
import { getAggregatedConditions, getConditions, getDiagnosis, getObbConditions, getReliabilityProfiles, getRoiEstimate, getSummary } from "./api";
import { ConditionsTable } from "./components/ConditionsTable";
import { DatasetUpload } from "./components/DatasetUpload";
import { ErrorReportTable } from "./components/ErrorReportTable";
import { ObbComparisonChart } from "./components/ObbComparisonChart";
import { PerformanceChart } from "./components/PerformanceChart";
import { QualityScoreCard } from "./components/QualityScoreCard";
import { RoiEstimateCard } from "./components/RoiEstimateCard";
import type { ConditionMetric, ConditionMetricAgg, DatasetSummary, DiagnosisResult, ReliabilityProfile, RoiEstimate } from "./types";

function App() {
  const [summary, setSummary] = useState<DatasetSummary | null>(null);
  const [conditions, setConditions] = useState<ConditionMetric[]>([]);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);
  const [roiEstimate, setRoiEstimate] = useState<RoiEstimate | null>(null);
  const [obbConditions, setObbConditions] = useState<ConditionMetric[]>([]);
  const [aggregated, setAggregated] = useState<ConditionMetricAgg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // 어느 클래스 구성의 성능 패턴 DB를 볼지. 같은 라벨 오류의 성능 저하가
  // 구성에 따라 크게 달라서(docs/21 Q) DB 자체를 갈아끼운다.
  const [profiles, setProfiles] = useState<ReliabilityProfile[]>([]);
  // 기본 프로파일의 클래스 구성과 같은 값으로 시작한다. 빈 문자열로 두면
  // select는 첫 항목("Car")을 보여주는데 상태는 ""라 화면과 상태가 어긋난다.
  const [classes, setClasses] = useState("Car");

  useEffect(() => {
    getReliabilityProfiles()
      // 목록을 못 받아도 기본 DB로는 볼 수 있어야 하므로 조용히 넘긴다
      .then((rows) => setProfiles(rows.filter((p) => p.available)))
      .catch(() => setProfiles([]));
  }, []);

  const load = (forClasses = classes) => {
    setLoading(true);
    setError(null);
    Promise.all([getSummary(), getConditions(forClasses), getDiagnosis(forClasses),
                 getRoiEstimate(), getObbConditions(), getAggregatedConditions()])
      .then(([s, c, d, r, obb, agg]) => {
        setSummary(s);
        setConditions(c);
        setDiagnosis(d);
        setRoiEstimate(r);
        setObbConditions(obb);
        // 3-seed 집계는 Car 단일 구성에서만 돌렸다. 다른 구성의 조건 위에
        // 겹쳐 그리면 조건 이름만 같고 실제로는 다른 실험의 오차막대를
        // 얹는 셈이 된다.
        setAggregated(forClasses && forClasses !== "Car" ? [] : agg);
      })
      .catch(() => setError("백엔드(http://localhost:8000)에 연결할 수 없습니다."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load("Car"); }, []);

  const switchClasses = (next: string) => {
    setClasses(next);
    load(next);
  };

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-kicker">AI 데이터 품질 인증 플랫폼</span>
        <h1>AIDA</h1>
        <div className="header-controls">
          {profiles.length > 1 && (
            <>
              <label htmlFor="class-config-select" className="sr-only">
                성능 패턴 DB의 클래스 구성
              </label>
              <select
                id="class-config-select"
                className="profile-select"
                value={classes}
                onChange={(e) => switchClasses(e.target.value)}
                disabled={loading}
              >
                {profiles.map((p) => (
                  <option key={p.name} value={p.classes.join(",")}>
                    {p.classes.join(" / ")}
                  </option>
                ))}
              </select>
            </>
          )}
          <button className="refresh-button" onClick={() => load()} disabled={loading}>
            {loading ? "불러오는 중..." : "새로고침"}
          </button>
        </div>
      </header>

      {error && <p className="error-banner">{error}</p>}

      {loading && !summary && <p className="loading-banner">데이터를 불러오는 중입니다...</p>}

      {summary && diagnosis && roiEstimate && (
        <main className="app-grid">
          <QualityScoreCard summary={summary} />
          <RoiEstimateCard estimate={roiEstimate} />
          <PerformanceChart conditions={conditions} aggregated={aggregated} />
          <ConditionsTable conditions={conditions} />
          <ObbComparisonChart aabbConditions={conditions} obbConditions={obbConditions} />
          <ErrorReportTable reports={diagnosis.error_reports} />
          <DatasetUpload />
        </main>
      )}
    </div>
  );
}

export default App;

