import { JudgingGuideline } from "./JudgingGuideline";

/**
 * "어떻게 분석하나요?" — 처음 쓰는 분석자를 위한 도움말.
 *
 * 사실만 적는다: 업로드 형식·상한은 backend `routers/upload.py`, 순서 버전은 `ranking.ts`, 키보드는
 * `ReviewQueue.tsx`, 판정 기준은 `JudgingGuideline`(= docs/manual-timing-pilot.md)과 같다.
 */
export function Guide() {
  return (
    <section className="card guide">
      <h2>어떻게 분석하나요?</h2>
      <p className="report-caveat">
        AIDA는 객체탐지 라벨 오류를 <b>찾아 재검수 순서를 제안하는 연구 프로토타입</b>이다. 결과는 확정 진단이 아니라
        "먼저 볼 후보"이고, 판정은 사람이 한다.
      </p>

      <ol className="guide-steps">
        <li>
          <h3>데이터 준비</h3>
          <ul>
            <li><code>images/</code>와 <code>labels/</code> 폴더를 담은 <b>zip</b> 하나. 폴더째 우클릭해 압축한 것도 된다.</li>
            <li>라벨은 YOLO 형식 — 이미지마다 같은 이름의 <code>.txt</code>, 한 줄에 <code>클래스 cx cy w h</code>(0~1로 정규화).</li>
            <li>클래스 이름을 알려면 <code>classes.txt</code>(또는 <code>data.yaml</code>)를 같이 넣는다. 기준 모델이 모르는 클래스가 있으면 경고한다.</li>
            <li>연속 프레임이면 <code>groups.json</code>(이미지 → 장면/주행 기록)을 넣을 수 있다. 평가할 때 묶음 단위로 센다.</li>
            <li>zip은 <b>200MB 이하</b>.</li>
          </ul>
        </li>
        <li>
          <h3>기준 모델(자) 고르기 — 가장 중요</h3>
          <p>AIDA는 기준 모델의 예측을 자로 삼아 라벨을 잰다. <b>자가 데이터와 맞지 않으면 결과가 크게 무너진다</b> —
            실험에서 상위 10% 정밀도가 맞는 자 94%, 다른 데이터로 학습한 자 26%였다. 내 데이터와 가장 비슷한 데이터로
            학습한 자를 고른다.</p>
        </li>
        <li>
          <h3>순서 버전 고르기</h3>
          <ul>
            <li><b>v1 · 기존 제품 순서</b> — 데이터셋에 많이 보이는 오류 유형의 후보를 먼저 보여 준다.</li>
            <li><b>v2 · 후보 단위 순서(시험)</b> — 후보마다 기준 모델과의 겹침(IoU)이 낮은 것부터. 데이터셋 판정이 순서를 바꾸지 않는다.</li>
          </ul>
          <p className="muted">자연 발생 오류로 한 예비 비교에서 v1이 단순 IoU 순서보다 나빴다. 어느 쪽이 나은지는 아직 검증 중이다.</p>
        </li>
        <li>
          <h3>결과 읽기</h3>
          <ul>
            <li><b>먼저 "자 적합"을 본다</b> — 기준 모델이 라벨 중 몇 %를 짚었는지. 낮으면 크기·위치 오류 판정은 믿기 어렵고,
              누락 판정이 상대적으로 버틴다.</li>
            <li>후보마다 <b>의심 유형</b>(가로·세로·크기·위치·중복·누락 등)과 이유가 붙는다.</li>
            <li>"계통적" 표시는 그 유형이 데이터셋 전체에 많이 보인다는 뜻이지, 그 후보가 오류라는 뜻이 아니다.</li>
          </ul>
        </li>
        <li>
          <h3>재검수하기</h3>
          <ul>
            <li>목록에서 후보를 고르면 이미지 위에 박스가 그려진다.</li>
            <li>키보드: <kbd>j</kbd>/<kbd>k</kbd> 줄 이동 · <kbd>f</kbd> 오류 · <kbd>d</kbd> 아님. 판정하면 다음 줄로 넘어간다.</li>
            <li>판정은 서버에 저장되어 새로고침 뒤에도 남는다. 지난 진단은 "지난 진단"에서 다시 연다.</li>
            <li>CSV로 내려받을 수 있다. <b>유형으로 걸러 둔 채 받으면</b> 빠진 줄이 "오류 아님"으로 오해될 수 있으니 주의.</li>
          </ul>
        </li>
      </ol>

      <details className="guide-details">
        <summary>평가용 가림 판정을 맡았다면 — 판정 지침</summary>
        <p className="muted">평가자는 받은 주소(<code>?evaluate=…</code>)로 들어간다. 점수·순위·방법은 일부러 보이지 않는다.</p>
        <JudgingGuideline />
      </details>

      <details className="guide-details">
        <summary>이 도구가 말하지 않는 것</summary>
        <ul>
          <li>품질 인증이나 검수 비용 절감을 보장하지 않는다. 실제 고객 데이터로 검증된 적이 없다.</li>
          <li>실험 수치 대부분은 "라벨에 일부러 넣은 오류를 찾는" 조건에서 나왔다. 자연 오류에서는 더 낮을 수 있다.</li>
          <li>연구용 비상업 프로토타입이다(KITTI·nuImages 비상업 조건, ultralytics AGPL-3.0).</li>
        </ul>
      </details>
    </section>
  );
}
