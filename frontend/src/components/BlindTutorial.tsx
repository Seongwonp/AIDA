import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * 가림 판정 첫 방문 튜토리얼.
 *
 * **실제 데이터 이미지를 쓰지 않는다** — 그림은 전부 손으로 그린 도식이다. 연습·평가 후보를
 * 보여 주면 판정 전에 그 후보를 미리 보게 된다. 방법 이름·점수·순위·후보 출처도 싣지 않는다.
 *
 * SVG에 `rect`·`stroke-width` 같은 속성을 쓰지 않는다 — 가림 검사가 DOM 전체에서 `width`·`scale`
 * 같은 낱말을 찾아 막는다. 굵기·크기는 CSS 클래스(App.css `.tut-*`)로 준다.
 */

/** 축에 맞춘 사각형 경로. `rect`를 쓰지 않으려고 둔다(위 주석). */
function box(x: number, y: number, w: number, h: number) {
  return `M${x} ${y}h${w}v${h}h${-w}Z`;
}

/** 옆에서 본 차 한 대 — 몸통과 바퀴 두 개. */
function Car({ x, y }: { x: number; y: number }) {
  return (
    <g className="tut-car" transform={`translate(${x} ${y})`}>
      <path d="M0 30 L8 14 Q12 8 20 8 L46 8 Q54 8 58 14 L66 22 L76 24 Q80 25 80 30 L80 38 L0 38 Z" />
      <circle cx="18" cy="38" r="7" />
      <circle cx="62" cy="38" r="7" />
    </g>
  );
}

function ColorsFigure() {
  return (
    <svg className="tut-figure" viewBox="0 0 300 120" role="img"
         aria-label="빨강 실선, 주황 점선, 파랑 상자를 그린 도식">
      <Car x={14} y={36} />
      <path className="tut-red" d={box(8, 40, 92, 44)} />
      <Car x={112} y={36} />
      <path className="tut-orange" d={box(106, 40, 92, 44)} />
      <path className="tut-tag" d={box(106, 22, 58, 16)} />
      <text className="tut-tag-text" x="110" y="34">라벨 없음?</text>
      <Car x={210} y={36} />
      <path className="tut-blue" d={box(204, 40, 92, 44)} />
      <text className="tut-caption" x="54" y="108" textAnchor="middle">빨강 실선</text>
      <text className="tut-caption" x="152" y="108" textAnchor="middle">주황 점선</text>
      <text className="tut-caption" x="250" y="108" textAnchor="middle">파랑</text>
    </svg>
  );
}

function TasksFigure() {
  return (
    <svg className="tut-figure" viewBox="0 0 300 120" role="img"
         aria-label="왼쪽은 차를 덜 감싼 빨강 상자, 오른쪽은 라벨 없는 차를 가리킨 주황 점선">
      <Car x={20} y={40} />
      {/* 앞부분이 밖으로 나간 상자 — "고쳐야 하는가"를 묻는다 */}
      <path className="tut-red" d={box(16, 44, 62, 40)} />
      <text className="tut-caption" x="70" y="108" textAnchor="middle">잘 감쌌나?</text>
      <Car x={180} y={40} />
      <path className="tut-orange" d={box(174, 44, 92, 44)} />
      <text className="tut-caption" x="220" y="108" textAnchor="middle">라벨이 빠졌나?</text>
    </svg>
  );
}

function NumberingFigure() {
  return (
    <svg className="tut-figure" viewBox="0 0 300 120" role="img"
         aria-label="한 차를 조금 다르게 가리킨 주황 점선 두 개가 같은 번호 M1을 받는 도식">
      <Car x={30} y={40} />
      <path className="tut-orange" d={box(24, 42, 92, 46)} />
      <path className="tut-orange" d={box(30, 38, 86, 46)} />
      <text className="tut-caption" x="70" y="108" textAnchor="middle">후보 둘 → 둘 다 M1</text>
      <Car x={196} y={40} />
      <path className="tut-orange" d={box(190, 44, 92, 44)} />
      <text className="tut-caption" x="236" y="108" textAnchor="middle">다른 차 → 새 객체(M2)</text>
    </svg>
  );
}

const STEPS: { title: string; body: ReactNode }[] = [
  {
    title: "상자 색이 뜻하는 것",
    body: (
      <>
        <ColorsFigure />
        <ul>
          <li><b>빨강 실선</b> — 지금 판정하는 기존 라벨.</li>
          <li><b>주황 점선</b> — 라벨이 빠졌다고 지목된 자리. 상자 품질이 아니라 그 자리에 라벨이 없는지를 묻는다.</li>
          <li><b>파랑</b> — 이 이미지에 이미 붙어 있는 다른 라벨.</li>
        </ul>
      </>
    ),
  },
  {
    title: "두 가지 일",
    body: (
      <>
        <TasksFigure />
        <ul>
          <li><b>기존 라벨(빨강)</b> — 이대로 학습에 써도 되면 <b>오류 아니었다</b>, 고쳐야 하면 <b>오류였다</b>.</li>
          <li><b>누락 확인(주황)</b> — 라벨돼야 할 객체가 있는데 파랑이 없으면 <b>오류였다</b>. 객체가 아니거나 이미 파랑이
            덮고 있으면 <b>오류 아니었다</b>.</li>
          <li><b>모르겠다</b> — 가림·해상도·애매한 경계 때문에 확신할 수 없을 때. 억지로 고르지 않는다.</li>
        </ul>
      </>
    ),
  },
  {
    title: "누락 객체 번호",
    body: (
      <>
        <NumberingFigure />
        <ul>
          <li>누락을 <b>오류였다</b>로 고르면 "어느 객체인가"를 정해야 저장된다.</li>
          <li>처음 보는 객체면 <b>새 객체</b> — M1, M2… 순으로 번호가 붙는다.</li>
          <li>다른 후보가 <b>같은 실제 객체</b>를 가리키면 이미 있는 번호(예: M1)를 고른다. 그래야 한 객체가 두 번 세지지 않는다.</li>
        </ul>
      </>
    ),
  },
  {
    title: "키보드와 가린 정보",
    body: (
      <>
        <ul className="tut-keys">
          <li><kbd>1</kbd> 오류였다</li>
          <li><kbd>2</kbd> 오류 아니었다</li>
          <li><kbd>3</kbd> 모르겠다</li>
          <li><kbd>←</kbd> 이전 · <kbd>→</kbd> 다음</li>
        </ul>
        <p>글자를 입력하는 칸에 있을 때는 단축키가 동작하지 않는다.</p>
        <p>
          후보를 누가·어떻게 골랐는지, 점수와 원래 순위는 <b>일부러 보여 주지 않는다</b>. 판정이 그 정보에 끌려가지 않게 하려는
          것이다. 판정 기준은 화면의 "판정 지침 보기"에 있다.
        </p>
      </>
    ),
  },
];

export function BlindTutorial({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const last = step === STEPS.length - 1;

  useEffect(() => {
    primaryRef.current?.focus();
  }, [step]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="tut-backdrop">
      <div className="tut-dialog" role="dialog" aria-modal="true" aria-labelledby="tut-title">
        <p className="tut-count">{step + 1} / {STEPS.length}</p>
        <h3 id="tut-title">{STEPS[step].title}</h3>
        <div className="tut-body">{STEPS[step].body}</div>
        <div className="tut-actions">
          <button type="button" className="judge-text-button" onClick={onClose}>건너뛰기</button>
          <span className="tut-spacer" />
          <button type="button" className="judge-nav-button" disabled={step === 0}
                  onClick={() => setStep(step - 1)}>
            이전 단계
          </button>
          <button type="button" ref={primaryRef} className="judge-nav-button judge-primary"
                  onClick={() => (last ? onClose() : setStep(step + 1))}>
            {last ? "판정 시작" : "다음 단계"}
          </button>
        </div>
      </div>
    </div>
  );
}
