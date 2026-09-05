import { useEffect, useState } from "react";
import { useReveal } from "../useReveal";

/**
 * 랜딩 화면.
 *
 * 여기 적힌 숫자는 전부 experiment/에서 실제로 잰 값이다(docs/21). 랜딩에
 * 그럴듯한 숫자를 지어 넣으면, 고객이 리포트를 열었을 때 화면의 수치와
 * 어긋나서 오히려 신뢰를 잃는다. 근거 문서 절 이름을 같이 적어 되짚을 수
 * 있게 했다.
 */

const STATS = [
  { value: 94.0, decimals: 1, suffix: "%", label: "상위 10% 재검수 정밀도", note: "자기 도메인 기준 모델 · 조건 29개 · 시드 7개" },
  { value: 27, decimals: 0, suffix: "종", label: "실측한 라벨 오류 조건", note: "기하·누락·중복·클래스 오기입" },
  { value: 10.2, decimals: 1, suffix: "σ", label: "기준 모델 선택의 효과", note: "도메인이 맞는 자 vs 어긋난 자" },
];

const ERROR_TYPES = [
  "가로 길이 어긋남", "세로 길이 어긋남", "전체 크기 어긋남", "중심점 이동",
  "회전 오류", "라벨 누락", "라벨 중복", "클래스 오기입",
];

const STEPS = [
  {
    n: "01",
    title: "데이터셋을 올린다",
    body: "이미지와 YOLO 라벨이 담긴 zip 하나면 된다. 정답을 따로 만들 필요가 없다.",
  },
  {
    n: "02",
    title: "기준 모델이 라벨을 잰다",
    body: "예측과 라벨을 박스 단위로 대조한다. 어느 기준 모델을 썼는지, 그 모델이 이 데이터에 맞는지까지 함께 알려준다.",
  },
  {
    n: "03",
    title: "재검수 목록을 받는다",
    body: "어느 이미지의 어느 박스를 왜 다시 봐야 하는지 심각도 순으로 준다. 전수 검사 대신 위에서부터 본다.",
  },
];

/** 0에서 목표값까지 세어 올린다. 움직임을 싫어하는 설정이면 그냥 목표값을 쓴다. */
function useCountUp(target: number, run: boolean): number {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!run) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setValue(target);
      return;
    }
    const started = performance.now();
    const DURATION = 900;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - started) / DURATION, 1);
      // 끝에서 부드럽게 멈추게 — 선형으로 세면 툭 끊긴다
      setValue(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, run]);

  return value;
}

function Stat({ value, decimals, suffix, label, note, run }:
              (typeof STATS)[number] & { run: boolean }) {
  const shown = useCountUp(value, run);
  return (
    <div className="stat">
      <strong className="stat-value">
        {shown.toFixed(decimals)}
        <span className="stat-suffix">{suffix}</span>
      </strong>
      <span className="stat-label">{label}</span>
      <span className="stat-note">{note}</span>
    </div>
  );
}

export function Landing({ onStart }: { onStart: () => void }) {
  // 첫 페인트 뒤에 숫자를 세기 시작한다 — 애니메이션이 렌더를 막지 않게.
  const [run, setRun] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setRun(true), 120);
    return () => clearTimeout(id);
  }, []);
  // 스크롤해서 들어온 것부터 하나씩 올라오게 한다
  useReveal();

  return (
    <div className="landing">
      <section className="hero">
        <span className="hero-kicker" data-reveal>AI 데이터 품질 진단 · 국방과학연구소 특허 10-2664201</span>
        <h1 className="hero-title" data-reveal data-reveal-delay="80">
          라벨이 틀렸는지<br />
          <em>모델에게 묻는다</em>
        </h1>
        <p className="hero-sub" data-reveal data-reveal-delay="160">
          정답 데이터를 새로 만들지 않고, 이미 학습된 모델의 예측을 자로 삼아
          어느 라벨을 다시 봐야 하는지 짚어냅니다. 전수 재검수 대신
          <strong> 위에서부터 필요한 만큼만</strong>.
        </p>
        <div className="hero-actions" data-reveal data-reveal-delay="240">
          <button className="cta" onClick={onStart}>데이터셋 진단하기</button>
          <a className="cta cta-ghost" href="https://github.com/Seongwonp/AIDA"
             target="_blank" rel="noreferrer">실험 기록 보기</a>
        </div>
      </section>

      <div className="marquee" aria-hidden="true">
        <div className="marquee-track">
          {[...ERROR_TYPES, ...ERROR_TYPES].map((t, i) => (
            <span key={i} className="marquee-item">{t}</span>
          ))}
        </div>
      </div>

      <section className="stat-band" data-reveal>
        {STATS.map((s) => <Stat key={s.label} {...s} run={run} />)}
      </section>

      <section className="steps" data-reveal>
        <h2 className="section-title">어떻게 동작하나</h2>
        <div className="step-grid">
          {STEPS.map((s, i) => (
            <article key={s.n} className="step" data-reveal
                     data-reveal-delay={i * 90}>
              <span className="step-n">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="evidence-teaser" data-reveal>
        <h2 className="section-title">가장 중요한 실측 결과</h2>
        <p className="teaser-lead">
          진단 품질을 정하는 건 알고리즘이 아니라 <strong>기준 모델이 그 데이터에
          맞는가</strong>였습니다. 같은 데이터를 자만 바꿔 진단했을 때:
        </p>
        <div className="teaser-bars">
          <div className="teaser-row">
            <span className="teaser-name">도메인이 맞는 기준 모델</span>
            <div className="teaser-bar"><div className="teaser-fill" style={{ width: "94%" }} /></div>
            <span className="teaser-num">94.0%</span>
          </div>
          <div className="teaser-row">
            <span className="teaser-name">아예 다른 데이터셋의 모델</span>
            <div className="teaser-bar"><div className="teaser-fill teaser-fill-weak" style={{ width: "26%" }} /></div>
            <span className="teaser-num">26.0%</span>
          </div>
        </div>
        <p className="teaser-foot">
          그래서 이 제품은 <strong>어느 기준 모델로 쟀는지 숨기지 않고</strong>,
          올린 데이터의 클래스를 읽어 맞는 모델을 추천하고, 모르는 클래스가 있으면
          경고합니다. (docs/21 AG·AI 실측)
        </p>
      </section>

      <section className="final-cta" data-reveal>
        <h2>지금 가진 데이터셋으로 확인해보세요</h2>
        <button className="cta" onClick={onStart}>데이터셋 진단하기</button>
      </section>
    </div>
  );
}
