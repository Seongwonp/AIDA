import { RANKING_V1, RANKING_V2, rankingLabel } from "../ranking";
import type { RankingInfo } from "../types";

/**
 * 이 목록을 어느 순위 버전으로 만들었는지와, 데이터셋 진단과 재검수 순서가 다른
 * 질문이라는 것 (docs/adr-ranking-separation.md).
 *
 * **v2가 낫다고 말하지 않는다.** 검증되지 않은 시험 버전이다.
 */
export function RankingNote({ ranking }: { ranking: RankingInfo | null | undefined }) {
  const version = ranking?.ranking_version ?? RANKING_V1;
  const legacy = !ranking || ranking.legacy;
  return (
    <div className="report-caveat ranking-note">
      <p>
        <strong>재검수 순서: {rankingLabel(version)}</strong>
        {legacy && " — 버전 기록이 없는 옛 결과라 v1으로 읽었습니다."}
      </p>
      <p>
        데이터셋 진단은 데이터셋 전체에서 어떤 오류 유형이 많아 보이는지를 말합니다.
        재검수 우선순위는 개별 후보를 어떤 순서로 볼지입니다.
      </p>
      {version === RANKING_V2 ? (
        <p>
          이 순서에서는 데이터셋 전체에서 많아 보인 유형이라는 이유로 그 유형의 후보를
          모두 위로 올리지 않습니다. 기존 라벨 후보는 기준 모델 예측과 덜 겹칠수록
          먼저(1 − IoU), 누락 후보는 따로 심각도 순입니다. 두 목록의 점수는 서로 비교하지
          않고 표에서는 번갈아 보여 줍니다. 시험 버전이며 v1보다 낫다는 검증은 없습니다.
        </p>
      ) : (
        <p>이 순서에서는 계통적이라고 본 유형의 후보를 모두 먼저 보여 줍니다.</p>
      )}
    </div>
  );
}
