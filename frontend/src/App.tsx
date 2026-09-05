import { useEffect, useState } from "react";
import "./App.css";
import { getAggregatedConditions, getConditions, getDiagnosis, getObbConditions, getReliabilityProfiles, getRoiEstimate, getSummary } from "./api";
import { ConditionsTable } from "./components/ConditionsTable";
import { DatasetUpload } from "./components/DatasetUpload";
import { ErrorReportTable } from "./components/ErrorReportTable";
import { Landing } from "./components/Landing";
import { MethodCard } from "./components/MethodCard";
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
  // 제품(진단)과 연구 근거를 갈라 놓는다. 기본은 진단 — 이 페이지에 처음
  // 온 사람이 하려는 일이다.
  const [tab, setTab] = useState<"diagnose" | "evidence">("diagnose");
  // 처음 온 사람에게는 랜딩을, 한 번 시작한 뒤에는 바로 도구를 보여준다.
  const [view, setView] = useState<"landing" | "app">("landing");
  // 화면을 오래 들여다보는 도구라 어두운 쪽을 원하는 사람이 있다.
  // 시스템 설정을 기본값으로 삼되, 고르면 그 선택을 기억한다.
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem("aida-theme");
      if (saved) return saved === "dark";
    } catch {
      /* 사생활 보호 모드 등에서 접근이 막힐 수 있다 */
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  });

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try {
      localStorage.setItem("aida-theme", dark ? "dark" : "light");
    } catch {
      /* 저장 못 해도 이번 세션에는 적용된다 */
    }
  }, [dark]);

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
        <button className="brand" onClick={() => setView("landing")}
                aria-label="처음 화면으로">
          <span className="app-kicker">AI 데이터 품질 인증 플랫폼</span>
          {/* 로고는 사이트 이름이지 페이지 제목이 아니다. 페이지의 h1은
              랜딩의 히어로 문장이 갖는다 — 한 화면에 h1이 둘이면 스크린
              리더가 문서 구조를 잘못 읽는다. */}
          <span className="brand-name">AIDA</span>
        </button>
        <div className="header-controls">
          {view === "app" && profiles.length > 1 && (
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
          <button
            className="icon-button"
            onClick={() => setDark((v) => !v)}
            aria-label={dark ? "밝은 화면으로" : "어두운 화면으로"}
            title={dark ? "밝은 화면으로" : "어두운 화면으로"}
          >
            {dark ? "☀" : "☾"}
          </button>
          {view === "app" && (
            <button className="refresh-button" onClick={() => load()} disabled={loading}>
              {loading ? "불러오는 중..." : "새로고침"}
            </button>
          )}
        </div>
      </header>

      {view === "app" && error && <p className="error-banner">{error}</p>}

      {view === "app" && loading && !summary && (
        <p className="loading-banner">데이터를 불러오는 중입니다...</p>
      )}

      {view === "landing" && <Landing onStart={() => setView("app")} />}

      {view === "app" && (
      <nav className="tab-bar" role="tablist" aria-label="화면 전환">
        <button
          role="tab"
          aria-selected={tab === "diagnose"}
          className={`tab ${tab === "diagnose" ? "tab-active" : ""}`}
          onClick={() => setTab("diagnose")}
        >
          진단
          <span className="tab-hint">내 데이터셋을 올려 재검수 목록을 받는다</span>
        </button>
        <button
          role="tab"
          aria-selected={tab === "evidence"}
          className={`tab ${tab === "evidence" ? "tab-active" : ""}`}
          onClick={() => setTab("evidence")}
        >
          근거
          <span className="tab-hint">그 판단이 무엇에 기반하는지</span>
        </button>
      </nav>
      )}

      {view === "app" && summary && diagnosis && roiEstimate && (
        <main className="app-grid">
          {tab === "diagnose" ? (
            <DatasetUpload />
          ) : (
            <>
              <MethodCard />
              {/* 이 둘은 **기준 실험 데이터**(KITTI 412장)의 요약이지 사용자가
                  올린 데이터가 아니다. 진단 탭에 두면 자기 데이터 점수로
                  읽히므로 근거 쪽에 둔다. */}
              <QualityScoreCard summary={summary} />
              <RoiEstimateCard estimate={roiEstimate} />
              <PerformanceChart conditions={conditions} aggregated={aggregated} />
              <ConditionsTable conditions={conditions} />
              <ObbComparisonChart aabbConditions={conditions} obbConditions={obbConditions} />
              <ErrorReportTable reports={diagnosis.error_reports} />
            </>
          )}
        </main>
      )}
    </div>
  );
}

export default App;

