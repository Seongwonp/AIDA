"""평가 집계의 **기준 구현** (docs/evaluation-protocol.md).

분석 스크립트마다 집계를 다시 짜면 규칙이 조금씩 갈린다. 여기 하나만 둔다.

모듈이 나뉜 이유는 각각 따로 검사하기 위해서다.

  schema      자료 구조와 검증 — 잘못된 상태를 표현하기 어렵게
  ranking     결정론적 순위와 동점 처리
  summary     한 방법·한 데이터셋의 요약
  paired      방법 간 짝지은 차이
  bootstrap   묶음 단위 재표집
  overall     데이터셋 동등 가중

**새 의존성을 넣지 않는다.** scipy는 이 환경에 없고 CI에는 numpy도 없다
(`requirements-ci.txt`). 부트스트랩은 표준 라이브러리로 짠다 — 재표집 단위와
짝지음이 맞는지는 검사로 고정한다.
"""
from .schema import (Adjudication, Judgement, Ranking,      # noqa: F401
                     ValidationError, split_judgements, validate)
from .ranking import rank_candidates                       # noqa: F401
from .summary import summarise                             # noqa: F401
from .paired import paired_difference                      # noqa: F401
from .bootstrap import paired_cluster_bootstrap            # noqa: F401
from .overall import equal_weight_overall                  # noqa: F401
