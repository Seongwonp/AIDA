import type { LabelDiagnosisResult } from "../types";

/**
 * 무엇으로 쟀는지, 그 자가 이 데이터에 맞는지, 유형마다 얼마나 믿을 수 있는지.
 *
 * AA·AD·AG가 세 번 같은 말을 했다 — 대상 분포에서의 실력이 전부다. 그래서
 * 진단 결과를 읽으려면 어느 자를 썼는지부터 알아야 한다. 예전에는 결과에
 * 그 정보가 아예 남지 않았다(docs/21 AE).
 *
 * DatasetUpload에서 떼어냈다. 그 파일이 업로드·진단 호출·오류 처리·결과 표
 * 셋까지 434줄이 됐는데, 기준 모델 이야기는 그 자체로 완결된 덩어리다.
 */
export function RulerCard({ result }: { result: LabelDiagnosisResult }) {
  return (
    <>
      {result.ruler && (
        <>
          <h3 className="subsection-heading">무엇으로 쟀는가 — 기준 모델</h3>
          <p className="report-caveat">
            진단은 기준 모델의 예측을 자로 삼아 라벨을 잽니다. 그래서 어느
            자를 썼는지가 결과를 읽는 데 필요합니다. 실측으로는 자의 학습량도
            클래스 폭도 그 자체로는 진단 품질을 정하지 않았습니다 — 정하는 것은
            이 데이터 분포에서의 실력입니다 (docs/21 AA·AD).
          </p>
          <div className="table-scroll">
            <table className="report-table">
              <tbody>
                <tr>
                  <th scope="row">기준 모델</th>
                  <td>{result.ruler.profile_label}</td>
                </tr>
                <tr>
                  <th scope="row">아는 클래스</th>
                  <td>{result.ruler.classes.join(", ")}</td>
                </tr>
                <tr>
                  <th scope="row">클래스 오기입 판정</th>
                  <td>
                    {result.ruler.class_aware
                      ? "함"
                      : "하지 않음 — 이 자가 아는 클래스 수가 데이터와 달라 위치만으로 진단합니다"}
                  </td>
                </tr>
                {result.ruler_fit &&
                 result.ruler_fit.matched_label_ratio !== null && (
                  <tr>
                    <th scope="row">이 데이터를 보고 있나</th>
                    <td>
                      라벨의{" "}
                      <b>{(result.ruler_fit.matched_label_ratio * 100).toFixed(0)}%</b>
                      를 이 모델이 짚어냈습니다
                      {result.ruler_fit.median_confidence !== null &&
                        ` (예측 신뢰도 중앙값 ${result.ruler_fit.median_confidence.toFixed(2)})`}
                      {(() => {
                        // 문턱을 0.5에 못 박으면 좁은 자에 오경보가 난다.
                        // 적합도는 자가 모르는 클래스의 라벨을 절대 못 채우므로,
                        // Car만 아는 자는 Car 비중이 곧 천장이다 (docs/21 AL).
                        const fit = result.ruler_fit!.matched_label_ratio!;
                        const ceiling = result.ruler_fit!.coverage_ceiling ?? 1;
                        const narrow = ceiling < 0.95;
                        const relative = fit / ceiling;
                        if (relative >= 0.5) {
                          return narrow ? (
                            <>
                              {" "}— 이 자가 아는 클래스가 라벨의{" "}
                              {(ceiling * 100).toFixed(0)}%뿐이라 적합도는 그
                              위로 못 올라갑니다. 그 안에서는{" "}
                              <b>{(relative * 100).toFixed(0)}%</b>를 짚었습니다.
                            </>
                          ) : null;
                        }
                        return (
                          <b className="fit-warn">
                            {" "}— {narrow
                              ? `이 자가 아는 클래스(라벨의 ${(ceiling * 100).toFixed(0)}%) 안에서도 절반을 못 짚었습니다.`
                              : "절반도 못 봤습니다."}{" "}
                            이 데이터에 맞는 기준 모델이 아닐 수 있고, 그러면
                            진단 결과를 믿기 어렵습니다.
                          </b>
                        );
                      })()}
                    </td>
                  </tr>
                )}
                <tr>
                  <th scope="row">학습 시드에 따른 흔들림</th>
                  <td>
                    ±{result.ruler.seed_spread_pp.toFixed(2)}%p — 같은 설정으로
                    다시 학습하기만 해도 이만큼 달라집니다 (시드 7개 실측)
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="report-caveat">
            "이 데이터를 보고 있나"는 <b>정답 없이 재는 값</b>입니다. 라벨과
            겹치는 예측이 얼마나 되는지만 세므로, 낮다고 해서 그게 전부 라벨
            오류라는 뜻은 아닙니다 — 자가 이 데이터의 물체를 못 보는 경우와
            구분되지 않습니다. 다만 <b>낮으면 어느 쪽이든 진단을 믿기 어렵다</b>는
            신호입니다. 실측으로는 데이터에 맞는 모델이 85.1%, 다른 데이터셋에서
            가져온 모델이 31.9%였습니다 (docs/21 AI).
          </p>
          <p className="report-caveat">
            <b>이 값은 "이 데이터에 맞는 자가 있는가"를 보는 신호이고, 품질
            눈금이 아닙니다.</b> 자 11종을 조건마다 견줘 봤습니다. 맞는 자가
            후보에 있으면 적합도가 그것을 잘 찾아냅니다(놓치는 정밀도 평균
            0.001). 그런데 <b>후보가 전부 어긋난 자면 적합도로 고르는 것이 거의
            소용없습니다</b> — 같은 실험에서 0.084로 84배 나빠졌습니다. 두 자의
            적합도 차이가 <b>5%p 미만이면 줄 세우지 마세요</b>, 그 아래에서는
            동전 던지기였습니다 (docs/21 AL·AM).
          </p>

          {result.ruler.unknown_class_ids.length > 0 && (
            <p className="error-banner">
              업로드한 라벨에 이 기준 모델이 모르는 클래스가 있습니다 (인덱스{" "}
              {result.ruler.unknown_class_ids.join(", ")}). 그 클래스의
              라벨은 오탐이 아니라 <b>아예 검사되지 않습니다</b> — 화면에
              아무 흔적도 남지 않으니, 해당 클래스를 아는 기준 모델을 고르세요.
            </p>
          )}
        </>
      )}

      {result.robustness.length > 0 && (
        <>
          <h3 className="subsection-heading">유형별 신뢰도 — 기준 모델이 맞지 않으면</h3>
          <p className="report-caveat">
            진단은 기준 모델의 예측을 자로 삼아 라벨을 잽니다. 그 모델이 이
            데이터와 다른 도메인에서 학습됐다면 유형마다 다르게 무너집니다.
            가운데 열은 <b>같은 데이터셋 안에서 프레임 구성만 바꿨을 때</b>,
            오른쪽 열은 <b>아예 다른 데이터셋(KITTI 자로 COCO를 진단)</b>일
            때의 실측값입니다 — 후자가 실제 고객 상황에 가깝고 훨씬 가혹합니다.
            기하 오류는 거의 전멸하고 라벨 누락만 살아남았습니다 (docs/21 AI).
          </p>
          <div className="table-scroll">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">오류 유형</th>
                  <th scope="col">도메인 맞을 때</th>
                  <th scope="col">프레임 구성만 다를 때</th>
                  <th scope="col">아예 다른 데이터셋</th>
                  <th scope="col">판단</th>
                </tr>
              </thead>
              <tbody>
                {[...result.robustness]
                  .sort((a, b) => b.shifted_domain - a.shifted_domain)
                  .map((r) => (
                    <tr key={r.suspicion}>
                      <td>{r.label}</td>
                      <td>{(r.matched_domain * 100).toFixed(1)}%</td>
                      <td>{(r.shifted_domain * 100).toFixed(1)}%</td>
                      <td>
                        {r.cross_dataset === null
                          ? "—"
                          : `${(r.cross_dataset * 100).toFixed(1)}%`}
                      </td>
                      <td className={
                        r.cross_dataset !== null && r.cross_dataset >= 0.65
                          ? "priority priority-높음"
                          : "priority-rationale"}>
                        {r.cross_dataset === null
                          ? (r.robust ? "도메인 무관하게 신뢰" : "기준 모델에 의존")
                          : r.cross_dataset >= 0.65
                            ? "데이터가 달라도 신뢰"
                            : "기준 모델에 크게 의존"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p className="report-caveat">
            이 표의 값은 <b>시드 하나에서 잰 것</b>입니다. 자를 학습 시드만
            바꿔 다시 만들면 자 전체로는
            {result.ruler ? ` ±${result.ruler.seed_spread_pp.toFixed(2)}%p` : " 수 %p"}
            {" "}흔들리는데, <b>유형별로는 그보다 훨씬 큽니다</b> — 도메인이
            어긋난 자로 실측했을 때 라벨 누락은 ±2.9%p로 비교적 안정적인 반면
            중심점 가로는 ±14.2%p까지 흔들렸습니다 (docs/21 AG, 시드 7개).
            개별 수치를 소수점까지 믿을 근거는 없고, 유형 사이의 큰 차이만
            읽으세요.
          </p>
        </>
      )}
    </>
  );
}
