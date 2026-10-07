# 위험 등록부

> 공개·배포 전에 확인해야 하는 위험을 적는다. 법적 판단이 아니다. 새 위험은 아래 표에 한 행씩 더한다.

| ID | 날짜 | 위험 | 현재 상태 | 공개·배포 전 할 일 |
|---|---|---|---|---|
| R-001 | 2026-10-07 | **git 기록에 nuImages에서 나온 화면 사진이 남아 있다.** 커밋 `3fa6d889`(2026-10-07 01:07 KST, "docs: add judging-screen screenshots …")가 `docs/assets/judging-screen.png`(blob `2f12a1763276b22845d5b73b89b676467c06ee81`, 30,572바이트)로 nuImages 이미지를 흐리게 처리한 판정 화면 캡처를 넣었다. 이 커밋은 `origin/main`에 푸시돼 있다. nuImages는 엄격한 비상업 조건이며, 그 이미지를 공개적으로 보이려면 Motional의 허가나 정확한 계약 조건을 따로 확인해야 한다(구체적 재배포 조건은 확정하지 않았다) | 커밋 `f05811bf`(10:09 KST)가 합성 데모 그림으로 바꿨다. **현재 HEAD(`51278bce`)의 `docs/assets`에는 그 blob이 없다**(2026-10-07 대조, 아래). **기록 재작성(rewrite)·강제 푸시는 사용자 결정으로 하지 않았다** | 저장소를 공개하거나 배포(포트폴리오 공개, 논문 부록 링크 등)하기 **전에** 이 커밋을 검토한다 — 기록 재작성 여부, 공개 범위, 원격 저장소 설정. 결정은 사용자가 한다 |

## R-001 대조 기록 (2026-10-07)

`git ls-tree HEAD docs/assets/`로 본 추적 그림과 blob:

| 파일 | blob | 내용 |
|---|---|---|
| `judging-screen.png` | `5d3b5ae3146d…` | 합성 데모(코드로 그린 도로·차, `demo_001.png`) — 눈으로 확인 |
| `judging-screen-existing.png` | `5f38588f34e9…` | 합성 데모 — 눈으로 확인 |
| `judging-tutorial-colors.png` | `45050088b928…` | 튜토리얼 도식(선 그림) — 눈으로 확인 |
| `judging-tutorial-missing.png` | `667b962c4ff0…` | 튜토리얼 도식(선 그림) — 눈으로 확인 |
| `aida-logo*.svg`, `aida-mark.svg` | — | 로고 벡터 |
| `diagram-*.png`, `experiment-results-*.png` | — | 2026-07~09 도식·결과 차트(nuImages 선택(2026-09-16) 전 커밋) |

- `git ls-tree -r HEAD`에서 blob `2f12a1763276b22845d5b73b89b676467c06ee81`을 찾은 결과 **0건**(트리 전체).
- `3fa6d889`의 튜토리얼 그림 blob(`bd79a50a…`, `b03f2cc9…`)도 HEAD에 없다(`f05811bf`에서 교체).
- 이 대조는 "HEAD에 그 blob이 없다"만 보인다. **기록에는 남아 있고**, 원격 저장소를 복제한 누구나 꺼낼 수 있다.
