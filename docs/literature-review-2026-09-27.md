> 저장소 밖에서 작성한 조사 보고서를 그대로 옮겼다(2026-09-27). §3.3의 대안 (d) "하한 구간" 명명과 §0-1의
> "유일한 적응" 표현은 Codex 검토에서 반려됐다 — [`unjudged-bootstrap-review-2026-09-27.md`](unjudged-bootstrap-review-2026-09-27.md).
> ObjectLab 기준선은 논문에서 "cleanlab 박스 단위 점수(badloc·swap)를 라벨마다 min으로 합친 이 연구의 적응"으로 부른다.

# AIDA 논문 — 선행연구·평가 방법론 조사 및 비판적 검토 (2026-09-27)

> 범위: 출처 조사와 설계 검토만. 구현·사전 등록 문서는 건드리지 않았다.
> 표기: **[사실]** = 원문에서 직접 확인한 내용, **[권고]** = 이 검토의 의견. 확인 상태는 *원문 전체 / 초록만 / 미확인*으로 구분한다.
> 인용문은 15단어 미만·출처당 1개 이하로 제한했다. DOI는 페이지에서 직접 읽은 것만 적었다.

---

## 0. 현재 설계에 영향을 주는 중요한 발견 5개

| # | 발견 | 근거 | 설계에 주는 의미 |
|---|---|---|---|
| 1 | **`1−min(badloc, swap)`는 ObjectLab 논문에도 cleanlab 공식 구현에도 없는 우리 구성이다.** ObjectLab이 정의하는 것은 *이미지 단위* 점수(오류 유형별 박스 점수를 softmin으로 이미지에 모으고, 세 유형을 기하평균)뿐이고, 평가도 전부 이미지 단위(AP, Precision@100, Precision@T)다. 박스 단위 badloc·swap·overlooked 점수 함수는 공식 API에 공개돼 있지만, 라벨 하나에 badloc과 swap을 합치는 공식 정의는 없다. 박스 단위로 ObjectLab 점수를 그대로 쓴 선행 사례(Penquitt et al. 2025)도 badloc과 overlooked를 **따로** 쓰고 합치지 않는다. | 논문 §2.1 Alg.1–4, §4.2; `rank.py`, `filter.py`, `summary.py` (원문 전체) | 논문에 "ObjectLab 기준선"이라고만 쓰면 부정확하다. "cleanlab이 공개한 박스 단위 badloc·swap 점수를 라벨마다 min으로 합친 우리의 적응(adaptation)"이라고 적어야 하고, 이 적응이 ObjectLab에 유리하지도 불리하지도 않다는 보장이 없음을 한계로 남겨야 한다. |
| 2 | **badloc은 "겹치는 같은 클래스 예측이 없거나, 같은 클래스 예측의 최대 확신도가 0.5 이하"면 1.0(깨끗)**을 준다. 즉 IoU 0 라벨뿐 아니라 *약한 예측만 겹치는 라벨*도 ObjectLab에는 보이지 않는다. swap은 "확신도 0.95 초과인 다른 클래스 예측"이 있어야만 1 미만이 된다. Car 단일 클래스 평가에서는 swap 분기가 사실상 작동하지 않으므로(다른 클래스 예측이 없음), **우리의 ObjectLab 기준선은 실질적으로 `1−badloc` 하나**가 되고, `all_label_iou`와의 차이는 (i) 유사도에 중심거리 항이 10% 섞임(α=0.9), (ii) 확신도 0.5 문턱, (iii) IoU 0·저확신 라벨을 맨 위가 아니라 맨 아래에 둠, 이 셋뿐이다. | `rank.py` `compute_badloc_box_scores`·`compute_swap_box_scores`, `constants.py` (원문 전체); 논문 Alg.2 else 분기 | D9(IoU 0 포함)와 결합하면 `all_label_iou`는 IoU 0 라벨을 상위에, ObjectLab은 최하위에 둔다. 이는 설계 문서(제안 D9 주석)가 이미 알고 있는 사실이지만, 논문에는 "이 비교는 IoU 0 라벨을 오류로 볼 것인가에 대한 두 입장의 비교이기도 하다"라고 명시해야 한다. 동시에 Car 단일 클래스에서 ObjectLab을 "상용 도구 전체"로 부르면 과장이다(swap·overlooked·이미지 점수는 쓰지 않음). |
| 3 | **기록 단위 부트스트랩에서 top-N을 다시 고르면 미판정 후보가 상위 N에 들어온다 — 저장소 코드로 확인.** `export_for_aggregation`은 미판정 후보(verdict=None)를 모집단 전체와 함께 내보내고, `bootstrap.py`는 재표본마다 top-N을 다시 고르며, `summary.py`는 미판정 후보를 `in_budget`에 넣되 `judged`에서 빼므로 그 후보는 **예산은 쓰고 수확은 0**으로 계산된다. 합성 자료로 돌린 결과 재표본당 상위 90 중 미판정 후보가 AIDA 쪽 평균 2.7–4.2건, 기준선 쪽 0.15–0.2건으로 **방법 간 비대칭**이었고, 그 결과 현재 코드의 구간이 전량 판정(oracle) 구간보다 하한이 1–2건 낮게 나왔다(3개 씨앗 중 2개). 점 추정치는 두 방법 상위 90이 모두 판정됐으므로 영향이 없다. | 저장소 `evaluation.py` L1158–1191, `bootstrap.py`, `summary.py` L74–77; 합성 시뮬레이션(아래 §3.3) | 현재 구현대로면 구간이 (a) 편향되고 (b) 편향의 방향이 방법 구조에 따라 달라 해석 불가. 사전 등록 확정 전에 판정 범위(top-M) 또는 분석 정의를 바꿔야 한다. 대안과 각각이 추정하는 양은 §3.3에 정리했다. |
| 4 | **비전 LLM은 박스 위치·가림 판정에서 사람과 큰 격차를 보인다는 직접 근거가 있다.** BLINK의 Object Localization(정답 박스 vs 가우시안 잡음을 준 박스 2지선다)에서 2024년 최전선 VLM은 사람(≈98–99%)에 훨씬 못 미쳤고(수치는 자동 추출 간 불일치 → PDF 재확인 필요), 가까이 붙은 도형의 겹침·접촉 판정도 약하며(BlindTest), 가림 벤치마크(O-Bench)에서는 **가림을 과소 보고**하는 계통적 편향이 있다. nuImages 박스는 **가림 부분까지 포함하는 amodal**이므로 이 편향은 우리 과제와 직접 충돌한다. 다만 박스를 그림으로 그려 넣고 고정 질문을 던지는 방식(DART)은 소규모에서 사람과 ~85% 일치를 보고했다. | BLINK(ECCV 2024), BlindTest(2024), O-Bench(2025), CAPTURe(ICCV 2025), SoM(2023), DART(2024) — 모두 원문 전체(HTML) | "AI 보조 판정은 2인 판정보다 약하다"는 현 설계의 자기 제한이 문헌과 일치한다. 프롬프트에 amodal 규칙을 명시하고, 박스는 좌표가 아니라 그림으로 넣으며, hold를 허용하고 원문 응답을 보존해야 한다. 일치도가 낮게 나와도 "AI가 틀렸다"고도 "사람이 틀렸다"고도 말할 수 없다는 점을 미리 적어야 한다. |
| 5 | **nuImages 공식 지침이 판정 지침의 상당 부분을 확정해 준다.** 가림 → 추정해서 포함(amodal), 잘림 → 이미지 경계에서 멈춤, 사이드미러·안테나 제외, 높이 10px 미만 미표기, 20% 미만 가시 미표기(확신 있으면 예외), 유리창 반사도 표기, 객체당 박스 1개, 인스턴스 마스크는 가시 부분만(≤2px). **nuImages에는 visibility 속성이 없다**(nuScenes 3D 전용). 반면 박스 **허용 오차(px/IoU), 가림 추정의 허용 범위, 픽업·밴 경계, 응급차량 우선순위**는 공식 문서에 없어 연구가 정해야 한다. | `instructions_nuimages.md`, `schema_nuimages.md`, `instructions_nuscenes.md` (원문 전체) | Car 30px 이상 범위는 공식 10px 규칙보다 엄격한 연구 선택임을 적을 것. "박스가 마스크보다 크다"는 오류 근거가 아니다. 판정 지침의 오류 정의(어느 정도 벗어나야 hit인가)는 공식 문서로 정당화할 수 없으므로 연구 정의로 선언해야 한다. |

---

## 1. 객체 탐지 라벨 오류 검출과 ObjectLab

### 1.1 출처 표

| 제목 (저자, 연도) | 원문 URL | 확인한 절/페이지 | 지원하는 주장 | AIDA 적용 한계 | 상태 |
|---|---|---|---|---|---|
| ObjectLab: Automated Diagnosis of Mislabeled Images in Object Detection **Data** (Tkachenko, Thyagarajan, Mueller, 2023; ICML DMLR 워크숍은 cleanlab.ai/research 기준) | https://arxiv.org/abs/2309.00832 · https://arxiv.org/pdf/2309.00832 | §1(오류 유형), §2.1 Alg.1–4·softmin·기하평균, §3, §4.1–4.2, Table 3 | 오류 유형 3종 정의; badloc은 같은 클래스 예측 중 IoU>0인 것과의 최대 유사도, 없으면 q*=1; swap은 확신도 τ↑ 초과 다른 클래스 예측 기준; overlooked는 예측 박스 단위; 이미지 점수 = softmin 후 기하평균; 평가 = 이미지 단위 AP·P@100·P@T | 박스 단위 결합 점수·박스 단위 평가 없음. 논문 텍스트의 α 표기가 코드와 반대 방향(논문 α=0.1, 코드 ALPHA=0.9가 IoU 가중)이므로 "α" 값을 논문에서 인용하지 말 것. 저자·제목은 위가 맞음(과제 지시문의 저자·제목은 부정확) | 원문 전체 |
| cleanlab `object_detection.rank` 문서 및 소스 (docs "stable"=v2.7.1 표시; GitHub master `version.py`=2.9.0) | https://docs.cleanlab.ai/stable/cleanlab/object_detection/rank.html · https://docs.cleanlab.ai/stable/tutorials/object_detection.html · https://github.com/cleanlab/cleanlab/blob/master/cleanlab/object_detection/rank.py · `filter.py` · `summary.py` · `internal/constants.py` | 함수별 반환 형태·NaN 규칙·기본 상수 | badloc: 같은 클래스 예측이 없거나 최대 확신도 ≤0.5 → 1.0; 확신도>0.5·IoU>0 예측과의 최대 유사도, 없으면 1.0. swap: 다른 클래스 라벨과 IoU≥0.95 겹치면 min_possible_similarity; 확신도>0.95 다른 클래스 예측이 없으면 1.0. overlooked: 확신도<0.95이거나 어떤 라벨과든 IoU>0이면 NaN. ALPHA=0.9, LOW=0.5, HIGH=0.95, TEMPERATURE=0.1, EUC_FACTOR=0.1, LABEL_OVERLAP=0.95. `find_label_issues`는 박스별 플래그를 내부 계산하지만 **이미지 단위 불리언만 반환** | 라벨 단위 결합 점수 없음. `rank.py`의 badloc docstring이 overlooked 문구를 복사한 오류가 있으므로 docstring 인용 금지. 실제 설치되는 cleanlab 버전을 명세에 적을 것(계획대로) | 원문 전체 |
| Identifying Label Errors in Object Detection Datasets by Loss Inspection (Schubert et al., 2023) | https://arxiv.org/abs/2303.06999 · pdf | §3.1.2, 3.2, 3.3, 3.5, Table 2–3 | 박스 단위 오류 유형 4종(drop/flip/shift/spawn); 박스 단위 순위; 실데이터에서는 **자기 방법의 상위 200건만** 사람이 판정해 정밀도 보고(VOC 71.5%, COCO 61.0%) | 방법 간 동일 예산 비교가 아님(자기 방법만 판정); 합성 노이즈 평가는 AUROC·max-F1; 출판 학회 미확인 | 원문 전체(학회 미확인) |
| Combating noisy labels in object detection datasets — CLOD (Chachuła et al., arXiv 2022/2023; Machine Learning 2026, DOI 10.1007/s10994-025-06976-x) | https://arxiv.org/abs/2211.13993 · https://link.springer.com/article/10.1007/s10994-025-06976-x | 방법 절(군집+confident learning), 평가 절 | 박스 단위 오류 유형(missing/spurious/mislabeled/mislocated); 박스 단위 AUROC; arXiv v3에 ObjectLab과의 AUROC 비교 있음 | 고정 예산 비교 없음; 저널판에 ObjectLab 비교가 남아 있는지는 **미확인** | arXiv 원문 전체 / 저널 초록만 |
| From Label Error Detection to Correction: A Modular Framework and Benchmark for Object Detection Datasets (Penquitt et al., arXiv 2508.06556, 2025–26) | https://arxiv.org/abs/2508.06556 · https://arxiv.org/html/2508.06556v2 | §III-B, IV-C, V-B, Table III, Fig. 7 | **ObjectLab을 박스 단위로 사용한 선례**: overlooked 점수는 탐지 박스에, `1−badloc`은 GT 박스에 따로 적용. 평가는 "발견한 누락 수 vs 주석 시간(초)" 곡선 | KITTI 보행자만; badloc과 swap 결합 없음; 고정 k에서의 방법 간 정밀도 비교 없음; 학회 미확인 | 원문 전체 |
| Pervasive Label Errors in Test Sets Destabilize ML Benchmarks (Northcutt, Athalye, Mueller, NeurIPS 2021 D&B) | https://arxiv.org/abs/2103.14749 | §3, Table 1·3, §6 | 후보를 순위로 뽑아 사람이 검증하고 "플래그 중 확인된 비율"을 보고; 제한된 검토 예산에서의 우선순위 부여를 명시적으로 권고 | 분류 과제; 방법 간 동일 k 비교 아님 | 원문 전체 |
| Confident Learning (Northcutt, Jiang, Chuang, JAIR 2021) | https://arxiv.org/abs/1911.00068 | §3.2, §5.1 Table 4, §5.2 | 정규화 마진으로 순위; 플래그 집합의 정밀도/재현율 | 분류 과제; precision@k 방법 간 비교 없음 | 원문 전체 |
| Deep Active Learning with Noisy Oracle in Object Detection (Schubert et al., 2023) | https://arxiv.org/abs/2310.00372 | §III.A–B, §IV, Fig. 4·6 | **검토 예산(λ)** 개념; 순위 제안의 주기별 정밀도 | 합성 노이즈; 점수 방법 간 동일 k 비교 아님 | 원문 전체(학회 미확인) |
| Annotation Error Detection: Analyzing the Past and Present… (Klie, Webber, Gurevych, 2022) | https://arxiv.org/abs/2206.02280 | §5 Metrics | flagger(P/R/F1) vs scorer(AP, **Precision@10%, Recall@10%**) 구분 — 고정 예산에서 상위 k%를 수정한다는 시나리오를 명시 | NLP 전용 | 원문 전체(학술지 미확인) |
| ActiveAED (Weber & Plank, 2023) | https://arxiv.org/abs/2305.20045 | ar5iv 전문 | 사람-루프 오류 탐지, 회차마다 상위 k건을 주석자에게 | NLP; AP/PR 곡선만 | 원문 전체 |

**찾지 못한 것(미확인):** nuImages/nuScenes 라벨 오류 감사 논문; 객체 탐지에서 여러 라벨 오류 점수 방법을 **같은 검수 예산 k에서 사람이 확인한 오류 수**로 직접 비교한 선행연구. 가장 가까운 것은 ObjectLab 자체의 이미지 단위 P@100(방법 간 비교 있음)과 Penquitt et al.의 "발견 수 vs 시간" 곡선(박스 단위, 방법 간 비교 있음, 고정 k 아님)이다.

### 1.2 검토

**[사실]** 우리 구성 `1−min(badloc, swap)`은 어느 정의에도 대응하지 않는다. 논문·구현 모두 유형별 박스 점수는 정의하지만 결합은 이미지 단위에서만 한다. `find_label_issues`가 내부적으로 박스별 임계값(클래스별 AP 기반 × 0.8)으로 유형별 플래그를 OR 하는 것이 가장 가까운 "박스 단위 결합"이지만, 점수가 아니라 불리언이고 외부에 노출되지 않는다.

**[사실]** Car 단일 클래스에서 swap 점수는 "확신도 0.95 초과인 **다른 클래스** 예측"이 있어야만 1 미만이 된다. 자(ruler)가 Car만 예측한다면 swap ≡ 1이고, `min(badloc, swap) = badloc`이다. 자가 다중 클래스를 내면 swap이 작동하지만 우리 모집단은 Car 라벨뿐이다. 논문에는 이 사실을 적어야 한다.

**[권고]** 논문 표기: "cleanlab 2.x의 박스 단위 `compute_badloc_box_scores`·`compute_swap_box_scores`(기본값)를 라벨마다 min으로 합쳐 `1−min`으로 정렬했다. 이는 우리의 적응이며 ObjectLab의 공식 산출물(이미지 단위 점수)이 아니다. 본 평가 조건(Car 단일 클래스)에서는 사실상 `1−badloc`과 같다." 그리고 ObjectLab의 이미지 단위 점수를 쓰는 대안(이미지를 고른 뒤 그 안의 라벨을 모두 검수)은 예산 단위가 달라 같은 표에 넣을 수 없음을 한계로 남긴다. 비교 방법을 바꾸라는 뜻이 아니다 — 지금 구성이 우리 질문(라벨 단위 검수 순서)에 맞는 유일한 적응이라는 점을 논증하면 된다.

**[권고]** ObjectLab 저자 표기는 Tkachenko·Thyagarajan·Mueller이며, 제목 마지막 단어는 "Data"다. 저장소 문서에 다른 표기가 있다면 고칠 것(이번 조사에서 확인한 범위에서는 `objectlab_baseline.py`에 저자 표기가 없다).

---

## 2. 사람 1인 + 비전 LLM 보조 판정

### 2.1 출처 표 (직접 근거)

| 제목 (저자, 연도, 학회) | 원문 URL | 확인한 절 | 지원하는 주장 | AIDA 적용 한계 | 상태 |
|---|---|---|---|---|---|
| BLINK: Multimodal LLMs Can See but Not Perceive (Fu et al., ECCV 2024) | https://arxiv.org/abs/2404.12390 · html v2 | 과제 정의(Object Localization), Table 1 | LVIS 이미지에서 GT 박스와 가우시안 잡음을 준 박스 중 정답 고르기(2지선다) — 사람 ≈98–99%, GPT-4V·Gemini Pro·Claude 3 Opus는 크게 미달. 전체 평균: 사람 95.7, GPT-4V 51.3 | **Table 1 과제별 수치가 자동 추출마다 달랐다(GPT-4V 37–50 사이)** — 인용 전 PDF에서 열 정렬 확인 필수. 2지선다 상대 판단이지 절대 "오류 여부" 판단이 아님; 잡음 크기가 실제 라벨 오류 크기와 다름; 2024년 모델 | 원문 전체(수치 재확인 필요) |
| Eyes Wide Shut? (MMVP; Tong et al., CVPR 2024) | https://arxiv.org/abs/2401.06209 | 9개 시각 패턴, Fig. 4 | 위치·관계·구조 등 세부 시각 특징을 VLM이 놓침; 사람 95.7 vs GPT-4V 38.7(추출마다 달라 재확인) | 박스·가림 과제 없음 | 원문 전체(수치 재확인) |
| Vision language models are blind (BlindTest; Rahmanzadehgervi et al., 2024) | https://arxiv.org/abs/2407.06581 | 과제 7종, 결과표, 근접도 분석 | 원이 겹치는지/닿는지, 선 교차 수 등 **가까이 붙은 도형** 판정이 약함(평균 58%); 멀면 거의 100% | 합성 도형; 사진 아님 | 원문 전체 |
| Beyond the Visible: Benchmarking Occlusion Perception in MLLMs (O-Bench; Liu et al., 2025) | https://arxiv.org/abs/2508.04059 | 과제 5종, 결과, 실패 분석 | 최고 모델 62.2 vs 사람 89.6; **가림이 없다고 답하는 보수적 편향**, 가림 비율 과소추정 | 합성 층 이미지; 주행 장면·박스 과제 아님 | 원문 전체 |
| CAPTURe (Pothiraj et al., ICCV 2025) | https://arxiv.org/abs/2504.15485 | 결과, 가림 정의 | 가려진 뒤를 추론하는 능력이 약함(GPT-4o 실사 sMAPE 14.75 vs 사람 3.79%) | 개수 세기 과제 | 원문 전체 |
| Set-of-Mark Prompting (Yang et al., 2023) | https://arxiv.org/abs/2310.11441 | RefCOCOg·Flickr30k 결과 | 이미지에 표시를 **그려 넣으면** 접지 정확도 급상승(75.6 vs 좌표 출력 25.7); 박스 표시 추가가 +5pt | 참조 표현 접지 과제; 박스 품질 판정 아님 | 원문 전체 |
| DART (Xin, Hartel, Kasneci, 2024) | https://arxiv.org/abs/2407.09174 | 의사 라벨 검토 절 | 박스를 그려 넣고 "너무 느슨/빡빡하지 않은가" 등 고정 질문 → 소규모에서 사람과 ~85% 일치 | 표본 크기 미기재, κ 없음, 다른 도메인·박스 규칙, 이미지 단위 통과/실패 | 원문 전체 |
| ClipGrader (Lu, Bian, Shah, 2025) | https://arxiv.org/abs/2503.02897 | 초록 | 박스 품질 채점은 학습 가능(COCO 91%) | 미세조정 CLIP; 대화형 VLM 제로샷 근거 아님 | 초록만 |
| MLLM-as-a-Judge (Chen et al., ICML 2024) | https://arxiv.org/abs/2402.04788 | 결과·편향 절 | 다중모달 심판도 위치·길이·자기선호 편향 | 모델 생성 텍스트 심사 | 원문 전체 |
| What's "up" with VLMs (Kamath et al., EMNLP 2023) · SpatialVLM (Chen et al., CVPR 2024) | https://arxiv.org/abs/2310.19785 · https://arxiv.org/abs/2401.12168 | 초록 | 공간 관계 약점 | 박스 과제 아님 | 초록만 |

### 2.2 출처 표 (간접 근거 — 텍스트 평가)

| 제목 | URL | 확인한 절 | 지원하는 주장 | 한계 | 상태 |
|---|---|---|---|---|---|
| Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena (Zheng et al., NeurIPS 2023 D&B) | https://arxiv.org/abs/2306.05685 | Table 5, 편향 절 | 사람–GPT-4 일치 66%(동점 포함, 무작위 33%) / 85%(동점 제외, 무작위 50%) vs 사람–사람 63/81%; **동점 처리에 따라 일치율이 ~20pt 달라짐**; 위치·장황함·자기강화 편향 | 텍스트 선호; 사람 여러 명 | 원문 전체 |
| Large Language Models are not Fair Evaluators (Wang et al., 2023) | https://arxiv.org/abs/2305.17926 | 초록 | 후보 순서를 바꾸면 판정이 뒤집힘 | 텍스트 쌍 비교 | 초록만 |
| ChatGPT outperforms crowd-workers (Gilardi et al., PNAS 2023) | https://arxiv.org/abs/2303.15056 | 방법·결과 | "정확도"를 훈련된 주석자와의 일치로 정의 — 우리가 피하려는 혼동의 실례 | 텍스트 | 원문 전체(arXiv) |
| Reliability without Validity (Norman, Rivera, Hughes, 2026) | https://arxiv.org/abs/2606.19544 | 초록 | 단순 일치가 κ보다 33–41pt 높음; 재검사 신뢰도 >0.95여도 위치 편향 — **신뢰도 ≠ 타당도** | 텍스트 | 초록만 |
| No Free Labels (Krumdick et al., 2025) | https://arxiv.org/abs/2503.05061 | 초록 | 심판이 스스로 풀 수 있는 문항에서만 전문가와 일치 | 텍스트 | 초록만 |
| Correlated Errors in LLMs (Kim et al., ICML 2025) | https://arxiv.org/abs/2506.07962 | 초록 | 모델 오류가 어려운 항목에 상관돼 몰림 | 모델–모델 상관; 사람–모델 확장은 추론 | 초록만 |

### 2.3 출처 표 (실행·기록)

| 제목 | URL | 지원하는 주장 | 상태 |
|---|---|---|---|
| How is ChatGPT's behavior changing over time? (Chen, Zaharia, Zou, 2023) | https://arxiv.org/abs/2307.09009 | 같은 호스팅 모델이 수개월 안에 달라짐 → 식별자·스냅샷·날짜 기록 | 초록만 |
| Quantifying LMs' Sensitivity to Spurious Features in Prompt Design (Sclar et al., ICLR 2024) | https://arxiv.org/abs/2310.11324 | 의미가 같은 서식 변화로 성능이 크게 흔들림 → 프롬프트 원문 고정·공개 | 초록만 |
| Testing the reliability of ChatGPT for text annotation (Reiss, 2023) | https://arxiv.org/abs/2304.11085 | 온도 0.25에서 반복 일치 α>0.9; 지시문 표현 간 α 0.24–0.7 → 온도 기록, 반복 실행 고려 | 원문 전체 |
| Model Cards (Mitchell et al., FAT* 2019) · NeurIPS Paper Checklist (LLM 사용 선언 항목) | https://arxiv.org/abs/1810.03993 · https://neurips.cc/public/guides/PaperChecklist | 모델 버전·날짜 문서화; 논문에 LLM 사용을 선언 | 초록/웹페이지 |

### 2.4 출처 표 (방법론 — 일치도 해석)

| 제목 | URL | 지원하는 주장 | 한계 | 상태 |
|---|---|---|---|---|
| Hallgren 2012, Computing inter-rater reliability… (TQMP 8(1)) | https://www.tqmp.org/RegularArticles/vol08-1/p023/p023.pdf | IRR은 같은 종류의 독립 평정자 간 일치; IRR 분석은 타당도 분석과 별개; κ의 prevalence·bias 문제 | "교환 가능한 평정자" 규칙을 명시적으로 쓰지는 않음 | 원문 전체 |
| McHugh 2012, Interrater reliability: the kappa statistic (Biochem Med 22(3)) | https://hrcak.srce.hr/89395 | 단순 일치율과 κ를 함께 보고; κ 등급 기준의 관대함 경고 | 타당도 논의 없음 | 초록/전문 일부 |
| Krippendorff 2004, Reliability in Content Analysis (HCR 30(3)) | https://academic.oup.com/hcr/article-abstract/30/3/411/4331534 | 신뢰도 계수의 조건 3가지 | "신뢰도는 타당도의 필요조건" 등 널리 알려진 문장은 저서에 있음 — **원문 미확인**, 인용 금지 | 초록만 |

### 2.5 검토

**[사실]** 박스 위치·가림·amodal 판정에 대해 문헌이 확립한 것: (a) 정답 박스와 잡음 박스의 2지선다에서 2024년 VLM은 사람과 큰 격차(BLINK), (b) 가까이 붙은 경계 판정이 약함(BlindTest), (c) 가림을 과소 보고(O-Bench)·가려진 뒤 추론이 약함(CAPTURe), (d) 좌표 대신 그림 표시가 훨씬 낫고(SoM), 그림+고정 질문 방식이 소규모에서 사람과 ~85% 일치(DART). **확립되지 않은 것:** 주행 이미지·amodal 규칙에서 실제 라벨 오류를 VLM이 판정한 사람–VLM κ; 2025–26 모델의 BLINK류 수치.

**[사실]** 사람–AI 일치도를 사람–사람 신뢰도나 정확도로 읽을 수 없는 이유는 세 출처를 합쳐야 성립한다: IRR ≠ 타당도(Hallgren) + 신뢰도 높은 심판도 편향 가능(Norman et al.) + "정확도"가 실은 주석자 일치인 사례(Gilardi). 한 문장으로 이를 말하는 원문은 찾지 못했다.

**[권고]** 논문 한계 문장은 이렇게 구성한다: "AI 판정자는 사람 판정자와 교환 가능한 평정자가 아니다(같은 과제군에서 계통적·비인간적 실패 양상이 문서화돼 있음: BLINK, BlindTest, O-Bench). 따라서 κ는 계산 가능하나 사람–사람 신뢰도의 대체물이 아니고, 참값이 없으므로 정확도도 아니다. 두 판정자가 같은 어려운 사례(심한 가림·잘림·30px 근처)를 보므로 오류가 상관될 수 있어(Kim et al.의 모델–모델 결과를 사람–모델로 확장한 추론) 일치가 정답의 독립 증거도 아니다."

**[권고]** 실행 명세에 넣을 것(각 항목의 근거): 박스를 그림으로 넣고 좌표 병기(SoM, DART); 프롬프트에 nuImages amodal·잘림·미러 제외 규칙을 명시(O-Bench의 가림 과소보고 편향 때문); 프롬프트 원문 고정·공개(Sclar, Reiss); 모델 식별자·스냅샷·날짜·온도·입력 해상도·추론 모드 기록(Chen et al., Model Cards, NeurIPS 체크리스트); 온도 0 또는 낮게, 가능하면 ≥3회 반복해 반복 일치도 보고(Reiss); 선택지(hit/miss/hold) 순서를 고정하되 문서화하고 유도적 표현 배제(Wang, Zheng); 거부·회피 응답을 hold로 사상하되 원문 보존(Zheng의 동점 처리 민감성). 이는 현 D8 명세와 충돌하지 않으며 빈칸(모델 식별자·프롬프트)을 채울 때 함께 적으면 된다.

---

## 3. 통계 설계

### 3.1 출처 표

| 제목 (저자, 연도, 학술지) | 원문 URL | 확인한 절 | 지원하는 주장 | 한계 | 상태 |
|---|---|---|---|---|---|
| High agreement but low kappa I (Feinstein & Cicchetti, J Clin Epidemiol 43(6), 1990) | https://www.sciencedirect.com/science/article/abs/pii/089543569090158L | 초록 | 주변합 불균형(낮은 유병률)이 κ를 끌어내리는 두 역설 | 초록만; 2×2 | 초록만 |
| High agreement but low kappa II (Cicchetti & Feinstein, 1990) | https://www.sciencedirect.com/science/article/abs/pii/089543569090159M | 초록; 공식은 SAS Global Forum 2009 paper 242-2009로 확인 | κ와 함께 **양성 일치 p_pos = 2a/(2a+b+c), 음성 일치 p_neg = 2d/(2d+b+c)** 보고 권고 | 2×2 전용 — hit vs 비-hit로 접어야 함 | 초록만(공식은 2차 출처) |
| Bias, prevalence and kappa (Byrt, Bishop, Carlin, 1993) | https://www.sciencedirect.com/science/article/abs/pii/089543569390018V | 초록; PI·BI·PABAK 공식은 Sim & Wright 2005·Shankar & Bangdiwala 2014로 확인 | PI=(a−d)/N, BI=(b−c)/N, PABAK=2P0−1 보고 | PABAK은 단순 일치율의 재척도일 뿐 독립 증거가 아님 | 초록만 |
| Gwet 2008 (Br J Math Stat Psychol 61(1)) + Handbook ch.5 | https://bpspsychub.onlinelibrary.wiley.com/doi/10.1348/000711006X126600 · https://www.agreestat.com/books/cac5/chapter5/chap5.pdf | 초록; 공식 | AC1은 극단 유병률에서 안정; 3범주에 자연 적용 | 우연 모형이 논쟁적; κ 대체 아님 | 초록+공식 |
| The kappa statistic in reliability studies (Sim & Wright, Phys Ther 85(3), 2005) | https://academic.oup.com/ptj/article/85/3/257/2805022 | 전문(Academia 사본) | PI·BI·κ_max·CI 보고; 범주 접기 경고; Table 8 표본 크기 | — | 원문 전체 |
| Hallgren 2012 | 위 §2.4 | 전문 | 결측이 많은 설계에는 Krippendorff α | — | 원문 전체 |
| Observer agreement paradoxes in 2×2 tables (Shankar & Bangdiwala, BMC MRM 14:100, 2014, DOI 10.1186/1471-2288-14-100) | https://link.springer.com/article/10.1186/1471-2288-14-100 | 전문 | 위 역설·PABAK·p_pos/p_neg·AC1을 한 곳에 정리 | 2차 정리 | 원문 전체 |
| Bootstrap Methods and their Application (Davison & Hinkley, 1997) | https://www.cambridge.org/core/books/bootstrap-methods-and-their-application/ED2FD043579F27952363566DC09CBD6A | 목차: Ch.3 §3.8 "Hierarchical variation", Ch.5 | 계층 자료의 재표집 장(章) 존재 | **내용 미확인** — 절 제목만 | 목차만 |
| Bootstrapping clustered data (Field & Welsh, JRSS-B 69(3), 2007) | https://academic.oup.com/jrsssb/article-abstract/69/3/369/7109361 | 초록 | 군집 부트스트랩이 변환·랜덤효과 모형 모두에서 일치 분산 추정 | 최소 군집 수 언급 없음(초록) | 초록만 |
| Bootstrap-based improvements for inference with clustered errors (Cameron, Gelbach, Miller, Rev Econ Stat 90(3), 2008) | https://ideas.repec.org/a/tpr/restat/v90y2008i3p414-427.html · NBER t0344 | 초록·기술 WP 전문 | 군집 5–30개는 "few"; 군집 수가 적으면 과대 기각 | 회귀 계수 설정; 우리 통계량에 wild bootstrap 직접 이식 불가 | 원문 전체(WP) |
| DiCiccio & Efron 1996, Bootstrap confidence intervals (Stat Sci 11(3)) | (Project Euclid 차단) | 2차 출처(arXiv 2404.12967, MedCalc)로 백분위 vs BCa 확인 | 백분위 구간은 1차 정확; BCa는 편향·가속 보정 | **원문 미확인** | 서지만 |
| ESL 2nd ed. §7.10.2 "The Wrong and Right Way to Do Cross-validation" · Ambroise & McLachlan 2002 (PNAS) | (원문 차단; CRAN `cv` vignette·Zhu et al. 2007로 확인) | — | 자료로 하는 선택 단계는 재표집 루프 **안**에 있어야 함 | 원문 미확인 | 미확인(원리는 2차 출처로 확인) |
| Retrieval evaluation with incomplete information (Buckley & Voorhees, SIGIR 2004) | https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=150469 | 전문 | MAP·P@k는 **미판정을 비관련으로 취급**; 판정 완전성이 떨어지면 시스템 순위가 불안정; bpref | 관련성 순위 평가; 오류 개수 지표 아님 | 원문 전체 |
| Alternatives to Bpref (Sakai, SIGIR 2007) · Sakai & Kando 2008 (Inf Retr 11(5)) | https://waseda.elsevierpure.com/en/publications/alternatives-to-bpref · Springer | 초록/일부 | **condensed list**: 미판정 문서를 목록에서 제거하고 계산 — 불완전 판정에 가장 강건 | 추정 대상이 "판정된 것 안에서의 성능"으로 바뀜 | 초록만 |
| Estimating AP with incomplete and imperfect judgments (Yilmaz & Aslam, CIKM 2006; KAIS 2008) · NIST infAP 설명 | https://www-nlpir.nist.gov/projects/tv2006/infAP.html | NIST 설명·KAIS 초록 | infAP: 판정이 풀의 무작위 표본이라는 가정 아래 전체 지표를 추정 | 우리 판정 집합은 무작위가 아니라 순위 의존(top-N 합집합)이라 가정 위배; 무작위 K 표본에만 적용 가능 | 초록+설명 |
| Evaluating evaluation metrics based on the bootstrap (Sakai, SIGIR 2006) | NII BOOTS 페이지 | 초록 | **토픽 단위** 짝지은 부트스트랩 검정 — 기록 단위 부트스트랩의 IR 유사체 | 절차 세부 미확인 | 초록만 |
| The abuse of power (Hoenig & Heisey, Am Stat 55(1), 2001) | https://www.zoology.ubc.ca/~bio501/R/readings/hoenig%20&%20heisey%202001%20am%20stat%20-%20fallacy%20of%20power%20calculations%20for%20data%20analysis.pdf | 전문 | 관측 검정력은 p값의 함수일 뿐; 비유의 결과를 "검정력 높으니 H0 지지"로 읽는 역설 | — | 원문 전체 |
| Beyond power calculations (Gelman & Carlin, PPS 9(6), 2014) | SAGE | 초록 | 관측 효과가 아니라 외부 근거로 효과크기를 정해 설계 분석 | 초록만 | 초록만 |
| Sample size justification (Lakens, Collabra 8(1), 2022) | https://online.ucpress.edu/collabra/article/8/1/33267/120491/Sample-Size-Justification | 전문 | **자원 제약**도 정당한 근거; 그때 보고할 것(임계 효과크기, 달성 가능한 CI 폭, 민감도 분석); 사후 검정력은 p 이상의 정보 없음; 파일럿 효과크기는 편향 | — | 원문 전체 |
| When power analyses based on pilot data are biased (Albers & Lakens, JESP 74, 2018) | https://www.casperalbers.nl/files/powerJESP2018.pdf | 전문 | 파일럿 기반 검정력 분석의 편향 2종; 최소 관심 효과·safeguard power 권고 | — | 원문 전체 |
| An agenda for purely confirmatory research (Wagenmakers et al., PPS 7(6), 2012) · The preregistration revolution (Nosek et al., PNAS 2018) | https://www.fon.hum.uva.nl/paul/methoden/lit/Wagenmakers2012.pdf · OSF preprint | 전문 / 초록 | 자료를 본 뒤 정한 분석은 탐색적으로 분리 보고 | — | 전체 / 초록만 |

### 3.2 κ와 단순 일치율 — 검토

**[사실]** 오류가 드물면 단순 일치율은 높고 κ는 낮게 나오는 역설이 잘 알려져 있고(Feinstein & Cicchetti I), 해법은 하나의 지수가 아니라 **p_pos·p_neg를 κ와 함께** 보고하는 것이다(II). PI·BI(Byrt)와 CI(Sim & Wright)도 함께 적으라는 권고가 있다. "hold/unsure" 판정을 κ에서 어떻게 다룰지 직접 다룬 원문은 찾지 못했다(미확인).

**[권고]** 30% 표본의 보고 세트: (1) 양측 hit·miss·hold 주변합과 PI·BI, (2) 분자·분모를 적은 단순 일치율, (3) 2범주(hit vs 비-hit) p_pos·p_neg·κ(CI)·PABAK(단순 일치율의 재척도임을 명기), (4) 3범주 κ와 범주별 특정 일치(p_pos의 다범주 확장 — 우리 확장, 출처 없음)와 AC1(3범주 자연 적용), (5) hold 처리 세 가지 중 최소 둘: hold를 3번째 범주로(판정 체계 전체의 일치), hold를 비-hit로 접기(1차 지표를 움직이는 결정의 일치), hold를 결측으로 제외(양측이 확정한 사례에서의 일치; Krippendorff α는 짝지을 값이 없는 단위를 자동 제외). 각각이 다른 양을 추정하므로 논문에 그렇게 적는다. 오류가 드물면 **p_pos가 핵심 수치**이고 p_neg는 거의 자동으로 1에 가깝다.

### 3.3 기록 단위 부트스트랩에서 미판정 후보 문제 — 검토

**[사실, 저장소 코드]** `export_for_aggregation`은 모집단 전체 후보를 `verdict: None`으로 내보내고 순위도 모두 붙인다. `paired_cluster_bootstrap`은 재표본마다 `top_n`으로 상위 N을 다시 고른다(요점 3 "처음부터 다시 계산"). `summarise`는 `picked` 중 `verdict is None`인 후보를 `in_budget`에는 넣고 `judged`·`hits`에서는 뺀다. 따라서 재표본에서 원래 순위 N 밖에 있던 미판정 후보가 상위 N에 들면, 그 자리는 **예산을 쓰고 0건**으로 센다. 이 처리는 IR에서 "미판정 = 비관련"으로 취급하는 것과 같고(Buckley & Voorhees), 편향과 불안정이 알려져 있다.

**[사실, 언제 생기는가]** 재표본이 순위 1..N을 바꿀 때마다 생긴다. 기록이 빠지면 그 기록의 후보가 사라져 순위 N+1 이하 후보가 올라오고, 기록이 두 번 뽑히면 그 후보가 두 자리를 차지해 다른 후보를 밀어낸다(중복 제거는 고유 오류 수에서만 하므로 자리 계산에는 두 벌이 모두 들어간다). 재표본 상위 N ⊆ 원래 판정 집합은 일반적으로 성립하지 않는다.

**[사실, 합성 시뮬레이션]** 저장소의 `evaluation` 모듈을 그대로 써서 합성 모집단(기록 35개, 이미지 6–10장/기록, 라벨 2–6개/이미지 ≈ 1,110 라벨, IoU 0 라벨 10%, AIDA 규칙이 라벨의 ~54%를 후보로 유지, 두 방법 모두 `1−iou` 정렬, 판정 집합 = 두 방법 상위 90 합집합 ∪ 무작위 50 ≈ 160건)에 2,000회 부트스트랩을 돌렸다(씨앗 3개). 결과:

| 씨앗 | 관측 차이(aida−base) | 현재 코드 구간 | 전량 판정(oracle) 구간 | condensed-list 구간 | 재표본당 상위 90 중 미판정 평균 (aida / base) |
|---|---|---|---|---|---|
| 1 | −1 | [−8, 5] | [−7, 5] | [−8, 5] | 3.9 / 0.2 |
| 2 | −3 | [−12, 4] | [−10, 5] | [−11, 4] | 4.2 / 0.15 |
| 3 | −2 | [−8, 4] | [−7, 7] | [−8, 6] | 2.7 / 0.2 |

읽는 법: 점 추정치는 두 방법 상위 90이 모두 판정됐으므로 영향이 없다. 구간은 현재 코드가 oracle보다 하한 1–2건·상한 0–3건 낮아 **AIDA 쪽으로 불리하게 이동**했다. 비대칭의 원인은 구조적이다 — 기준선의 새 진입 후보(전체 순위 91–110)는 대개 AIDA 상위 90에 이미 들어 판정돼 있지만, AIDA의 새 진입 후보는 규칙을 통과한 라벨 중 전체 순위 ~200 이하라 어느 목록에도 없다. 실제 자료에서 방향과 크기는 다를 수 있다(규칙 필터의 강도, 기록당 후보 분포, 오류율에 따라). **이 수치는 기제와 방향 가능성을 보이는 예시이지 실제 자료의 추정이 아니다.**

**[권고 — 대안과 각각이 추정하는 것]** (출처 있는 것은 표시; 나머지는 이 검토의 추론)

| 대안 | 무엇을 하나 | 무엇을 추정하나 | 비용·한계 | 근거 |
|---|---|---|---|---|
| (a) 더 깊게 판정: 방법별 상위 M(M>N) | 라벨 없이 순위만으로 같은 기록 부트스트랩을 미리 돌려 "재표본 상위 N ⊆ 원래 상위 M"이 예컨대 99% 이상 성립하는 M을 고르고, 그 M까지 판정 | **사전 등록한 목표량 그대로**(재선정을 포함한 상위 N 수확의 변동) | 판정 (M−N)×방법 수 증가; 나머지 1% 재표본은 여전히 미판정 진입(보고) | 선택 단계가 루프 안에 있어야 한다는 원리(ESL 7.10.2·Ambroise–McLachlan, 원문 미확인·원리는 2차 확인) |
| (b) condensed-list: 판정된 풀 안에서만 순위·상위 N | 기록을 재표집하되 미판정 후보를 목록에서 제거하고 상위 N 계산 | **조건부 양**: "판정된 풀에서 N개를 고를 때"의 수확 변동 — 모집단 상위 N 수확이 아님. 풀을 더 많이 차지한 방법에 유리 | 추가 판정 없음; 시뮬레이션에서는 현재 코드와 거의 같은 구간(풀 구성이 비대칭이라 편향이 남음) | Sakai 2007, Sakai & Kando 2008(초록) |
| (c) 고정 목록 부트스트랩 | 원래 상위 N 목록을 고정하고 기록만 재표집해 그 목록 안 hit 수 차이의 분포 | 관측된 목록의 수확이 **기록 표본에 따라** 얼마나 흔들리는가; 재선정 변동은 빠져 구간이 좁음 | 추가 판정 없음; 전량 판정 보장; "순위 재선정 효과"를 말할 수 없음 | Field & Welsh(군집 부트스트랩 일반), Sakai 2006(토픽 단위 짝지은 재표집) |
| (d) 미판정 = 비오류로 두고 **하한**으로 보고, 또는 대치 | 현재 코드 결과를 "하한 구간"으로 명명; 또는 진입한 미판정 후보를 무작위 K 표본의 오류율(순위대·방법별 층화 가능)로 베르누이 대치하고 민감도 표(0 / K 표본 오류율 / 상한값) | 대치 모형 아래의 수확 — infAP의 가정("미판정도 판정된 것과 같은 비율로 관련")과 유사 | K=50이 순위 N 근처 층의 오류율을 대표하지 못할 수 있음; 방법별 미판정 비율을 반드시 함께 보고 | Buckley & Voorhees(비관련 취급의 편향), NIST infAP 설명 |
| (e) 기록 단위 짝지은 차이의 정확 순열/부호 검정 | 고정 목록 안에서 기록별 hit 차이를 계산해 순열 검정 | 기록 안에서 두 방법이 교환 가능하다는 귀무가설에 대한 증거; 수확 차이의 CI는 아님 | 가정이 적고 전량 판정; 효과 크기 구간이 없어 (c)와 보완 | (출처 없음 — 표준 비모수 검정) |

**[권고]** 사전 등록에 넣을 최소 변경: 1차 구간의 정의를 (a) 또는 (c) 중 하나로 확정하고, 현재 코드의 처리는 폐기하거나 (d)의 "하한"으로 이름을 바꾼다. (a)를 택하면 M 선택 절차(라벨 없는 순위 전용 부트스트랩)를 판정 전에 돌려 M과 포함률을 8절 점검표에 적는다. 어느 쪽이든 재표본당 방법별 "상위 N 중 미판정 수"를 기록·보고하도록 `summarise` 결과를 부트스트랩 출력에 남기는 것이 필요하다(현재는 차이만 남김). 이 검토는 구현을 바꾸지 않았다.

**[권고]** 기록 수가 30–60개 수준이면 Cameron et al.의 "few clusters(5–30)" 범위에 걸치므로 백분위 구간의 포함률 저하 경고를 적고, BCa 또는 스튜던트화 구간을 민감도로 보탤 수 있다(DiCiccio & Efron 원문 미확인). 이산 개수 통계량이라 동점 처리가 BCa의 편향 보정에 영향을 준다.

### 3.4 사후 검정력 vs 표본 크기 계획 — 검토

**[사실]** 관측 효과로 계산한 사후 검정력은 p값의 결정적 함수라 정보를 더하지 않으며, 비유의 결과의 해석에 쓰면 역설이 생긴다(Hoenig & Heisey; Lakens). 파일럿(prelim1) 효과크기로 후속 연구 표본을 정하면 두 가지 편향이 든다(Albers & Lakens). 자원 제약은 정당한 표본 크기 근거이며, 그때는 임계 효과크기·달성 가능한 CI 폭·민감도 분석을 보고한다(Lakens).

**[권고]** 논문에서 N=90·표본 300장은 "자원 제약(판정자 1인의 연속 판정 길이·드라이런 시간)"으로 정당화하고, 관측 효과의 사후 검정력은 계산하지 않는다. 후속 연구 표본 크기는 최소 관심 효과(예: 검수 예산당 오류 몇 건 차이가 실무적으로 의미 있는가)나 safeguard 추정(관측 차이 CI의 보수적 끝)으로 정하고, 별도 절에 둔다. 저장소 `power-sensitivity`·`n-required-plan` 문서가 관측 효과 기반이라면 이 구분을 적용해야 한다(문서 내용은 이번에 검토하지 않았다).

---

## 4. nuImages 주석 규칙

### 4.1 출처 표

| 문서 | URL | 확인한 절/필드 | 확인한 내용 | 상태 |
|---|---|---|---|---|
| nuImages annotator instructions | https://github.com/nutonomy/nuscenes-devkit/blob/master/docs/instructions_nuimages.md | Bounding Boxes(General/Detailed), Instance Segmentation, Attributes, Surfaces | 가림 → 가려진 부분을 best guess로 포함; 잘림 → 이미지 경계에서 멈춤; 높이 <10px 미표기; 가시 <20% 미표기(확신 있으면 예외); 사이드미러·안테나 제외한 모든 말단 포함; 유리창 반사 표기; 객체당 박스 1개; 야간 차량은 등화 한 쌍이 보일 때만; 마스크는 가시 부분만(≤2px); nuScenes 클래스 전부 계승, 속성은 상위집합(+응급등 점멸/비점멸, 지면 위/아래) | 원문 전체(핵심 문장 직접 재확인) |
| nuImages schema | https://github.com/nutonomy/nuscenes-devkit/blob/master/docs/schema_nuimages.md | `object_ann`, `category`, `attribute`, `sample_data` | `bbox`는 "Annotated amodal bounding box" [xmin, ymin, xmax, ymax] 정수; **visibility 테이블 없음**; 해상도는 `sample_data.width/height`로 레코드별 | 원문 전체 |
| devkit `nuimages.py` | https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuimages/nuimages.py | `render_image` | bbox를 PIL rectangle에 그대로 (left, top, right, bottom)으로 전달; 클리핑·검증 없음 | 원문 전체 |
| nuScenes annotator instructions (클래스 정의) | https://github.com/nutonomy/nuscenes-devkit/blob/master/docs/instructions_nuscenes.md | 클래스 정의, visibility, 속성 | Car/Van/SUV = 개인용 차량(세단·해치백·왜건·밴·미니밴·SUV·지프); Truck = 화물용(픽업·로리·세미 트랙터); Pickup Truck이 별도 항목으로도 존재; Construction Vehicle은 화물 운반 트럭 제외; 버스는 >10인; Police/Ambulance는 모든 유형; visibility 4구간은 **nuScenes 3D 전용** | 원문 전체(`vehicle.*` 토큰 문자열은 이 문서에 없음 — 매핑 미확인) |
| nuScenes Revisited (Fong, Liong, Tan, Caesar, arXiv 2512.02448, 2025) | https://arxiv.org/html/2512.02448v1 | nuImages 절 | 93k 주석 이미지(각 13프레임 클립), ~75% 능동학습 선택·~25% 균일; nuScenes와 같은 라이선스; QA 절차는 문서화되지 않았다고 명시 | 원문 전체 |
| nuScenes (Caesar et al., CVPR 2020) | https://arxiv.org/abs/1903.11027 | 라이선스·주석 절 | CC BY-NC-SA 4.0; nuImages 언급 없음 | 원문 전체 |
| nuscenes.org/nuimages · terms-of-use | — | — | JS 렌더링·프록시 차단으로 **읽지 못함**. "800k 전경 객체·100k 시맨틱 마스크"·1600×900은 공식 페이지에서 미확인 | 미확인 |

### 4.2 검토

**판정 지침에 그대로 옮길 수 있는 것 [사실]:** 위 §0 발견 5의 목록 전부. 특히 (i) "가려진 부분 포함"이 규칙이므로 가림 때문에 박스가 가시 실루엣보다 큰 것은 오류가 아니다; (ii) 잘린 객체의 박스가 경계에서 멈추는 것은 규칙이고, 경계를 넘는 박스는 규칙 위반이지만 스키마·코드가 클리핑을 강제하지 않는다; (iii) 미러·안테나를 뺀 박스는 오류가 아니다; (iv) 반사 라벨은 그 자체로 허위 양성이 아니다; (v) 마스크와 박스 범위가 다른 것은 설계다.

**공식 문서만으로 확정할 수 없는 것 [사실: 없음이 확인됨]:** 박스 허용 오차(px 또는 IoU); 가림 추정이 얼마나 벗어나야 오류인가(특히 카메라 반대쪽으로 가려진 깊이 방향); 20% 가시의 측정 기준; 픽업·크루캡·화물 밴의 car/truck 경계 및 "Pickup Truck" 항목의 토큰 매핑; 순찰 세단·구급 승용차의 응급 클래스 우선순위; 차량 운반차 위의 차·쇼룸 안의 차·광고판·장난감; 주차장 뒷줄의 원경 차량; 속성 토큰 철자(`vehicle.parked` 등은 릴리스 `attribute.json`에서 확인 필요).

**[권고]** 판정 지침에 "연구 정의" 절을 두고 위 항목을 명시적으로 정한 뒤, 이 정의가 nuImages 공식 규칙의 해석이 아니라 연구의 결정임을 적는다. 30px 범위도 공식 10px 규칙보다 엄격한 연구 선택으로 적는다. 가림 관련 hit 판정은 "amodal 추정이 지침의 허용 범위를 벗어남"으로만 정의할 수 있고, 그 허용 범위는 우리가 정하는 것이므로 판정자 1인의 주관이 개입하는 지점임을 한계에 남긴다.

---

## 5. 설계를 지지하는 근거와 반대 근거 (요약)

| 설계 요소 | 지지 | 반대·주의 |
|---|---|---|
| 고정 예산 N에서 사람이 확인한 고유 오류 수 | ObjectLab 자체가 P@100·P@T(이미지 단위)로 방법을 비교; Klie et al.의 scorer 평가(P@10%); Northcutt et al.의 "제한된 검토 예산" 권고 | 객체 탐지에서 박스 단위·방법 간·동일 k 비교의 직접 선례는 찾지 못함; Penquitt et al.은 k 대신 시간축을 씀 |
| ObjectLab 기준선(`1−min(badloc, swap)`) | 박스 단위 badloc·swap 함수가 공식 API에 있음; Penquitt et al.이 박스 단위 badloc을 그대로 씀 | 결합 방식은 우리 것; Car 단일 클래스에선 사실상 `1−badloc`; IoU 0·저확신(≤0.5) 라벨을 깨끗으로 두므로 `all_label_iou`와 정반대 방향 — 설계가 이미 아는 사실이지만 논문에 명시 필요 |
| IoU 0 포함·고정 씨앗 동점(D9) | 동점·순서가 결과를 바꾼다는 일반 원리(저장소 기존 출처) | ObjectLab은 IoU 0 라벨을 사실상 평가 대상에서 제외하는 도구이므로 "포함"이 그 기준선에는 중립이 아님 — 보고 항목(상위 90 중 IoU 0 수)이 이를 드러냄 |
| 사람 1인 + VLM 30% 보조 | VLM이 박스·가림 판정에 약하다는 직접 근거가 "보조·탐색적" 자리매김과 일치; 그림 표시+고정 질문 방식의 선례(SoM, DART) | 사람–사람 기준선이 없어 Zheng et al.식 나란한 비교가 불가; 일치도가 낮아도 어느 쪽 문제인지 말할 수 없음; 오류 상관 가능 |
| κ + 단순 일치율 | 함께 보고하라는 표준 권고(McHugh, Sim & Wright) | 드문 오류에서 κ 역설 → p_pos·p_neg·PI·BI 없이 κ만 보고하면 오독; hold 처리 원문 없음 |
| 기록 단위 짝지은 부트스트랩, 재표본마다 top-N 재선정 | 군집 재표집(Field & Welsh)과 선택 단계 내부화(ESL) 원리에 부합 | **미판정 후보 진입 문제**(코드로 확인, 시뮬레이션에서 방법 비대칭); 기록 수가 적으면 백분위 구간 포함률 저하 |
| Δ 없음·방향 예측 없음·탐색적 한계 유지 | Wagenmakers et al., Nosek et al.: 자료 전에 정한 것만 확인적 | 분석 정의(대안 (a)–(e)) 선택 자체를 판정 전에 확정해야 탐색적 분리가 가능 |

---

## 6. 인용 전 재확인이 필요한 항목

1. BLINK Table 1 과제별 수치(자동 추출 간 GPT-4V Object Localization 37.21 vs 50.40; Random 25 vs 50) — PDF 열 정렬 직접 확인.
2. MMVP GPT-4V 수치(38.7 vs ~60).
3. Chachuła et al. 저널판에 ObjectLab 비교가 남아 있는지.
4. Krippendorff 저서의 "신뢰도는 타당도의 필요조건" 문장 — 원문 미확인이므로 인용하지 말 것.
5. DiCiccio & Efron 1996, ESL §7.10.2, Ambroise & McLachlan 2002 — 원문 접근 차단; 인용하려면 원문 확인.
6. nuScenes "Pickup Truck" 항목의 `vehicle.truck` 매핑, 속성 토큰 철자 — 릴리스 `category.json`·`attribute.json`에서 확인.
7. nuImages 공식 페이지 통계(800k 객체, 1600×900) — 공식 페이지 미확인.
8. ObjectLab 논문의 학회(ICML 2023 DMLR)는 cleanlab.ai/research 기준이며 arXiv Comments 줄은 읽지 못함.

## 7. 이 검토가 하지 않은 것

- 구현·사전 등록 문서 수정. 시뮬레이션 스크립트(`sim_unjudged.py`)는 저장소 밖 임시 파일이며 결과 해석에만 썼다.
- 비교 방법 변경 제안. §3.3의 대안은 "무엇을 추정하는가"를 가르는 것이지 AIDA에 유리한 쪽을 고르라는 것이 아니다 — 시뮬레이션에서 현재 코드가 AIDA에 불리했지만, 실제 자료에서는 반대일 수 있다.
- 저장소의 `power-sensitivity`·`n-required-plan`·`current-evidence` 문서 내용 검토.
