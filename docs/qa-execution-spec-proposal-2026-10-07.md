# 사전 등록 11절 실행 명세 — 채울 값 제안 (2026-10-07)

> **사전 등록 문서([qa-preregistration.md](qa-preregistration.md))는 아직 고치지 않았다.** 아래 값은 사용자 결정(2026-10-07)을
> 정리한 것이고, 사용자가 최종 확인하면 11절에 그대로 옮겨 커밋한다. 그 커밋이 있어야 `nuimages_eval_sample.py`가 val을 연다.

| 11절 항목 | 값 | 근거 |
|---|---|---|
| 자 `car_v1_e100` SHA-256 | `fffecf529a6df1a87d5f10ec2f5613d55adaf69ec09fd48996ecd467584110cc` (이미 기입) | `experiment/planning_evidence/desktop_environment_2026-10-06.json` |
| AI 판정자 | `claude-sonnet-5`, 1회·후보마다 새 대화, 전체 장면 + 크롭 2장, 비용 상한 $10. 온도·해상도는 환경이 노출하는 값만 기록(미노출이면 "미노출") | 사용자 결정 2026-10-07 |
| AI 프롬프트 원문 | [ai-adjudicator-prompt-draft.md](ai-adjudicator-prompt-draft.md)의 시스템·사용자 메시지 블록 그대로 | 유리 반사 규칙 반영 |
| 판정 상한 C | **1,000건.** 묶음을 얼린 판정 목록(원래 상위 N ∪ K ∪ 고정 재표본 추가)이 C를 넘으면 **판정을 시작하지 않고** 사전 등록을 개정해 새 평가 ID로 다시 얼린다(N을 결과를 보고 줄이지 않는다). 약 150건 단위로 나눠 쉬며 판정한다 | 연습: 후보당 중앙값 1.6초, 재표본 추가 +93%(N=20) — `practice1_judging_summary_2026-10-07.json`, `practice1_bundle_2026-09-29.json` |
| 사람 판정 지침 부록 | 아래 | 연습 판정 뒤 |

## 사람 판정 지침 부록 (연습에서 헷갈린 사례)

1. **유리에 비친 차량.** nuImages 어노테이션 지침: "If an object is reflected clearly in a glass window, then the reflection
   should be annotated." → 선명하게 비친 차에 붙은 기존 라벨이 상자를 잘 감쌌으면 *오류 아니었다*, 선명히 비친 차에 라벨이
   없으면 누락 후보는 *오류였다*. 흐릿하거나 차체·물웅덩이 등에 비친 모호한 상은 *모르겠다*. 출처: nuscenes-devkit
   `docs/instructions_nuimages.md` (Bounding Boxes 절). 연습 판정은 이 규칙을 정하기 전에 했다 — 연습 자료라 분석에 쓰지 않는다.

## 한계로 적을 것

- AI 판정자가 이 연구 설계에 참여한 모델과 같은 계열(Claude)이다. 일치도는 보고만 하고 1차 분석은 사람 판정 원본이다.
