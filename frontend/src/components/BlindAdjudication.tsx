import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getBlindQueue, postActivity, putAdjudications } from "../api";
import { makeActivityLogger, queueKey } from "./activityLog";
import { API_BASE_URL } from "../api";
import { AdjudicationView } from "./AdjudicationView";
import { JudgingGuideline } from "./JudgingGuideline";
import { BlindTutorial } from "./BlindTutorial";
import { rememberTutorial, tutorialSeen } from "./blindTutorialStorage";
import {
  advanceTarget,
  ALL_JUDGED_MESSAGE,
  blockedIds,
  BUNDLE_MISMATCH_MESSAGE,
  bundleCompleteMessage,
  bundleHeader,
  bundleLabel,
  bundleSpans,
  DAMAGED_MESSAGE,
  firstIncompleteSpan,
  judgedInSpan,
  LAYER_MISSING,
  nextUnjudgedIndex,
  nextUnjudgedInSpan,
  resumeIndex,
  spanAt,
  type BundleSpan,
  HASH_CONFLICT_MESSAGE,
  MISSING_NEEDS_OBJECT,
  makeAdjudicationSender,
  missingObjects,
  nextMissingObject,
  progress,
  questionFor,
  saveMessage,
  toJudgements,
  toRequest,
  unjudgedCount,
  VERDICT_BUTTONS,
  type BlindCandidate,
  type EvalVerdict,
  type Judgements,
  type SaveState,
} from "./blindAdjudicationLogic";

/**
 * 가림 판정 화면 — **평가용이지 제품 기능이 아니다.**
 *
 * 우리가 만든 순서가 실제로 쓸모 있는지 재려면, 그 순서를 **모르는 채로** 각
 * 후보가 진짜 오류였는지 판정해야 한다. 순위와 점수를 보면서 매긴 판정으로는
 * 그 순위를 평가할 수 없다 — 자기가 만든 답을 자기가 확인해 주는 셈이다.
 *
 * **무엇을 가리고 무엇을 못 가리는지 정확히 적는다.**
 *
 * | | |
 * |---|---|
 * | 가린다 | 어느 방법이 추천했는지, 점수, 원래 순위, **세부 의심 유형** |
 * | 못 가린다 | **기존 라벨 검수인지 누락 객체 검수인지** |
 *
 * 못 가리는 쪽은 숨길 수가 없다 — 판정 작업 자체가 다르기 때문이다. 기존
 * 라벨은 "이 라벨이 틀렸는가"를 묻고 누락은 "여기 객체가 빠졌는가"를 묻는다.
 * 이것까지 숨기면 판정자가 무엇을 판단해야 할지 모른다. **그래서 "의심 유형을
 * 완전히 가렸다"고 말하지 않는다.**
 *
 * **이 화면이 있다고 "자연 오류에서 검증했다"가 되지 않는다.** 생긴 것은
 * 판정을 기록할 길이고, 판정 자체는 아직 개발자가 한다. 독립된 판정자가
 * 정답을 확정한 것이 아니다.
 *
 * 그래서 재검수 화면(`ReviewQueue`)을 고쳐 쓰지 않고 따로 만든다. 한 화면에
 * 두 모드를 넣으면 가림이 켜졌는지 아닌지가 상태에 달리게 되고, 그건 결과가
 * 휘었는지 나중에 알 수 없다는 뜻이다.
 */
// 단추 글자가 곧 판정 결과다(오류 있음 = hit · 오류 없음 = miss · 판단 보류 = hold).
// 대응표는 `blindAdjudicationLogic.ts`의 `VERDICT_BUTTONS` 한 곳에만 둔다.
const VERDICTS = VERDICT_BUTTONS;

const KEY_VERDICT: Record<string, EvalVerdict | undefined> = Object.fromEntries(
  VERDICTS.map((v) => [v.key, v.verdict]),
);

export function BlindAdjudication({
  datasetId,
  evaluationId,
}: {
  datasetId: string;
  evaluationId: string;
}) {
  const [candidates, setCandidates] = useState<BlindCandidate[]>([]);
  const [judgements, setJudgements] = useState<Judgements>({});
  const [hash, setHash] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [damaged, setDamaged] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [save, setSave] = useState<SaveState>("idle");
  // `null`은 **띄울 후보가 없다**는 뜻이다 — 아직 안 불러왔거나 전부
  // 판정했거나. 0번으로 갈음하면 이미 판정한 후보에 시간이 쌓인다.
  const [cursor, setCursor] = useState<number | null>(null);
  // 저장 응답은 렌더가 끝난 뒤에 온다. 그때의 **최신** 목록·판정·자리를 봐야 자동 이동이 맞는 곳으로
  // 간다 — 클로저의 값은 판정을 누른 순간의 것이다.
  const candidatesRef = useRef<BlindCandidate[]>([]);
  candidatesRef.current = candidates;
  const judgementsRef = useRef<Judgements>({});
  judgementsRef.current = judgements;
  const cursorRef = useRef<number | null>(null);
  cursorRef.current = cursor;
  // 묶음 표시 계획(사전 등록 D5·D6). `null`이면 옛 묶음 — 한 목록 그대로.
  const [spans, setSpans] = useState<BundleSpan[] | null>(null);
  const spansRef = useRef<BundleSpan[] | null>(null);
  spansRef.current = spans;
  // 방금 마친 묶음. 값이 있고 `cursor`가 `null`이면 묶음 완료 화면이다(쉬어도 되는 자리).
  const [bundleDone, setBundleDone] = useState<number | null>(null);
  // 저장이 진행 중인 후보. 그 후보에 대한 판정 입력은 응답이 올 때까지 무시한다 — 연타·키 반복으로
  // 같은 판정이 두 번 저장되거나, 자동 이동이 두 번 일어나지 않게.
  const savingIdRef = useRef<string | null>(null);
  // 마지막으로 저장에 실패한 후보. "다시 시도"가 성공하면 그 후보에서 자동 이동한다.
  const failedIdRef = useRef<string | null>(null);
  // 후보를 화면에 띄운 순간. 후보별 시간은 여기서부터 잰다.
  const openedRef = useRef<string | null>(null);
  // 첫 방문이면 튜토리얼을 띄운다. 저장소가 막혔으면 `tutorialSeen`이 false라 띄운다.
  const [tutorial, setTutorial] = useState(() => !tutorialSeen());
  const closeTutorial = useCallback(() => {
    rememberTutorial();
    setTutorial(false);
  }, []);

  // 작업 기록. **계산은 여기서 안 한다** — 무슨 일이 언제 있었는지만 남기고,
  // 시간 계산은 `experiment/evaluation/activity.py`가 나중에 한다
  // (docs/pilot-evaluation-plan.md).
  const hashRef = useRef("");
  hashRef.current = hash;
  const log = useMemo(
    () =>
      makeActivityLogger(
        (events) => postActivity(datasetId, evaluationId, hashRef.current, events),
        // **평가마다 따로 둔다.** 한 키에 모으면 다른 평가의 이벤트가 섞여
        // 묶음 해시가 안 맞아 통째로 거부당한다.
        { storageKey: queueKey(datasetId, evaluationId) },
      ),
    [datasetId, evaluationId],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    // **평가가 바뀌면 이전 평가의 흔적을 전부 지운다.**
    //
    // 후보를 남기면, 새 목록을 기다리는 동안 지난 평가의 후보가 판정 가능한
    // 채로 화면에 있고 그 판정은 새 묶음 해시로 저장을 시도한다.
    //
    // **경고와 오류도 같이 지워야 한다.** 실패한 평가에서 정상 평가로 옮겼는데
    // 오류 화면이 남으면 다음 평가를 아예 못 연다. 손상 표시나 409 경고가
    // 따라오면, 멀쩡한 묶음을 두고 "바뀌었다"고 말하는 셈이다.
    setCandidates([]);
    setJudgements({});
    setCursor(null);
    setSpans(null);
    setBundleDone(null);
    openedRef.current = null;
    setHash("");
    setError(null);
    setConflict(false);
    setDamaged(false);
    setSave("idle");
    savingIdRef.current = null;
    failedIdRef.current = null;

    // 목록을 기다린 시간은 **사람이 판정한 시간이 아니다.** 그 구간을 가려낼
    // 수 있게 조회의 시작과 끝을 남긴다.
    log.record("queue_load_started");
    getBlindQueue(datasetId, evaluationId)
      .then((data) => {
        if (cancelled) return;
        log.record("queue_load_succeeded");
        const restored = toJudgements(data.candidates);
        let loadedSpans: BundleSpan[] | null;
        try {
          loadedSpans = bundleSpans(data.candidates, data.bundles);
        } catch {
          // 묶음이 목록과 어긋나면 판정을 받지 않는다 — 어느 후보가 어느 묶음인지 믿을 수 없다.
          setError(BUNDLE_MISMATCH_MESSAGE);
          return;
        }
        setCandidates(data.candidates);
        setSpans(loadedSpans);
        setHash(data.candidate_set_hash);
        setDamaged(data.damaged);
        setJudgements(restored);
        // **아직 판정 안 한 첫 후보에서 이어 한다.** 0번부터 시작하면 두 번째
        // 세션에서 이미 판정한 후보를 넘기는 시간이 그 후보들의 판정 시간에
        // 다시 쌓여, 후보당 시간이 부풀고 N이 작아진다. 묶음이 있으면 미판정이 남은
        // 가장 앞 묶음의 첫 미판정이다(`resumeIndex`).
        setCursor(resumeIndex(data.candidates, restored, loadedSpans));
      })
      .catch(() => {
        if (cancelled) return;
        log.record("queue_load_failed");
        setError("판정 목록을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [datasetId, evaluationId, log]);

  useEffect(() => {
    // **여기서 새 세션을 시작하지 않는다.** 세션은 logger를 만들 때 하나
    // 생기고, 그건 페이지 한 번 뜰 때 한 번이다. effect마다 새로 시작하면
    // 개발 모드의 StrictMode가 effect를 두 번 돌려 **세션 수가 두 배로**
    // 잡힌다 — dry pilot에서 2회 방문이 4세션으로 나와 잡혔다.
    log.record("session_started");

    const onVisibility = () => {
      const visible = document.visibilityState === "visible";
      log.record("visibility_changed", null, { visible });
      // 숨는 순간이 마지막 기회일 수 있다 — 모바일은 여기서 페이지를 버린다.
      if (!visible) void log.flush();
    };
    const onFocus = () => log.record("focus_changed", null, { focused: true });
    const onBlur = () => log.record("focus_changed", null, { focused: false });
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);

    // 기록을 주기적으로 보낸다. 판정 흐름과 엮지 않는다 — 기록 전송이
    // 실패해도 판정은 이어져야 한다.
    const timer = window.setInterval(() => void log.flush(), 10_000);

    // **창이 닫히는 중에는 보통의 요청이 취소된다.** 브라우저가 페이지를
    // 버리면서 진행 중인 fetch도 같이 버린다. `pagehide`에서 `sendBeacon`으로
    // 넘기면 문서가 사라진 뒤에도 마저 보내 준다.
    //
    // 응답을 못 받으므로 큐에서 지우지 않는다 — 서버가 이미 받았다면 다음
    // 접속의 재전송이 `event_id`로 걸러진다.
    const onPageHide = () => {
      log.record("session_ended");
      log.flushOnExit(
        `${API_BASE_URL}/api/datasets/${datasetId}/evaluations/${evaluationId}/activity`,
        (events) => ({ candidate_set_hash: hashRef.current, events }),
      );
    };
    window.addEventListener("pagehide", onPageHide);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("pagehide", onPageHide);
      window.clearInterval(timer);
      log.record("session_ended");
      void log.flush();
    };
  }, [log, datasetId, evaluationId]);

  useEffect(() => {
    // **실제로 띄운 후보만** 기록한다. 완료 화면에서는 아무것도 안 띄우므로
    // `candidate_opened`도 안 남는다.
    const id = cursor === null
      ? null
      : candidates[cursor]?.canonical_candidate_id ?? null;
    if (id && id !== openedRef.current) {
      openedRef.current = id;
      log.record("candidate_opened", id);
    }
  }, [candidates, cursor, log]);

  const sendToServer = useMemo(
    () =>
      makeAdjudicationSender(async (rows: ReturnType<typeof toRequest>) => {
        try {
          await putAdjudications(datasetId, evaluationId, hash, rows);
        } catch (e) {
          // 409는 후보 목록이 바뀐 것이다. 재시도로 풀리지 않으니 구분해 알린다.
          const status = (e as { response?: { status?: number } })?.response?.status;
          if (status === 409) setConflict(true);
          throw e;
        }
      }),
    [datasetId, evaluationId, hash],
  );

  const blocked = blockedIds(candidates, judgements);
  const stats = progress(candidates, judgements);
  const current = cursor === null ? undefined : candidates[cursor];
  const left = unjudgedCount(candidates, judgements);
  const span = spanAt(spans, cursor);
  // 묶음 완료 화면: 방금 마친 묶음이 있고 띄운 후보가 없다. 전부 끝났으면 완료 화면이 대신 뜬다.
  const finishedSpan = cursor === null && bundleDone !== null && spans ? spans[bundleDone] ?? null : null;
  const upcoming = spans ? firstIncompleteSpan(candidates, judgements, spans) : null;
  const bundleBreak = !loading && finishedSpan !== null && upcoming !== null;
  const done = !loading && candidates.length > 0 && cursor === null && !bundleBreak;

  /**
   * 판정을 저장한다. `id`는 이 저장을 일으킨 후보, `advance`가 참이면 **저장이 성공한 뒤** 그 후보에서
   * 다음 미판정 후보로 옮긴다(뒤에 없으면 앞에서 찾는다 — "다음 미판정"과 같은 규칙, 전부 판정했으면
   * 완료 화면). 묶음이 있으면 **그 묶음 안에서만** 찾고, 묶음이 다 찼으면 묶음 완료 화면에서 멈춘다
   * (`advanceTarget`) — 다음 묶음은 판정자가 "다음 묶음 시작"을 눌러야 시작한다.
   *
   * 옮기지 않는 경우:
   * - 저장 실패 — 지금 후보에 남아 "다시 시도"를 누를 수 있게 한다.
   * - 누락을 오류 있음으로 골랐는데 객체 번호를 아직 안 정했다 — 저장 자체를 안 한다(`blockedIds`).
   *   번호를 고르고 그 저장이 성공해야 옮긴다.
   * - 응답이 오기 전에 판정자가 직접 다른 후보로 옮겼다 — 한 번 더 옮기면 본 적 없는 후보를 건너뛴다.
   * - 그 사이 다른 평가로 바뀌었다.
   *
   * 자동 이동은 기존 이벤트 `moved_next`에 `meta: { auto: true }`를 붙여 남긴다 — 서버가 받는 이벤트
   * 이름은 그대로고, 손으로 옮긴 것(`meta` 없음)과 가를 수 있다.
   */
  const persist = (
    next: Judgements,
    { id = null, advance = false, retry = false }:
      { id?: string | null; advance?: boolean; retry?: boolean } = {},
  ) => {
    if (blockedIds(candidates, next).length > 0) {
      // 누락 hit인데 어느 객체인지 안 정했다. **보내지 않는다.**
      setSave("idle");
      return;
    }
    const list = candidates;
    setSave("saving");
    if (retry) log.record("save_retried");
    log.record("save_started");
    savingIdRef.current = id;
    void sendToServer(toRequest(list, next)).then((ok) => {
      log.record(ok ? "save_succeeded" : "save_failed");
      if (savingIdRef.current === id) savingIdRef.current = null;
      if (candidatesRef.current !== list) return;           // 다른 평가로 바뀌었다
      if (!ok) {
        failedIdRef.current = id;
        setSave("failed");
        return;
      }
      if (failedIdRef.current === id) failedIdRef.current = null;
      // **다 끝났으면 기다리지 않고 보낸다.** 기록은 12건이 쌓이거나 10초마다
      // 나가는데, 판정자는 완료 화면에서 곧 창을 닫는다. 닫을 때의 전송
      // (`pagehide`·`sendBeacon`)은 보장되지 않는다 — prelim1에서 마지막
      // 후보의 판정은 저장됐는데 그 후보의 기록은 하나도 서버에 없었다.
      const flushNow = unjudgedCount(list, next) === 0;

      const latest = judgementsRef.current;
      const at = id === null ? -1 : list.findIndex((c) => c.canonical_candidate_id === id);
      const stillHere = at !== -1 && cursorRef.current === at;
      const settled = id !== null && latest[id]?.verdict != null
        && !blockedIds(list, latest).includes(id);
      if (advance && stillHere && settled) {
        // 묶음이 있으면 **그 묶음 안에서만** 옮긴다. 묶음이 다 찼으면 묶음 완료 화면에서 멈춘다.
        const target = advanceTarget(list, latest, at, spansRef.current);
        const index = target.kind === "candidate" ? target.index : null;
        log.record("moved_next", null, target.kind === "bundle_complete"
          ? { auto: true, bundle_complete: target.bundle }
          : { auto: true });
        // 같은 응답으로 두 번 옮기지 않게 바로 적어 둔다(렌더 전에 또 불려도 `stillHere`가 거짓이 된다).
        cursorRef.current = index;
        setBundleDone(target.kind === "bundle_complete" ? target.bundle : null);
        setSave(index === null ? "saved" : "advanced");
        setCursor(index);
      } else {
        setSave("saved");
      }
      if (flushNow) void log.flush();
    });
  };

  // **상태 갱신 함수 안에서 저장하지 않는다.** 갱신 함수는 React가 두 번 부를
  // 수 있어(개발 모드의 StrictMode) 같은 판정이 두 번 나간다.
  const apply = (next: Judgements, id: string, advance: boolean) => {
    judgementsRef.current = next;     // 같은 렌더 안의 연속 입력도 최신 판정 위에 쌓이게
    setJudgements(next);
    persist(next, { id, advance });
  };

  const judge = (id: string, verdict: EvalVerdict | null) => {
    // 이 후보의 저장이 아직 진행 중이면 무시한다 — 연타·반복 입력이 두 번 저장·두 번 이동을 만든다.
    if (savingIdRef.current === id) return;
    const base = judgementsRef.current;
    const before = base[id] ?? { verdict: null };
    // 오류가 아니라고 바꾸면 붙여 둔 누락 객체도 뗀다 — 남겨 두면 판정과
    // 이름이 어긋난 채로 저장된다.
    const missingObject = verdict === "hit" ? before.missingObject ?? null : null;
    // **판정 유형을 기록에 남긴다.** 화면에는 안 띄운다 — 요약이 뜨면
    // 판정자가 그걸 보고 다음 판단을 조절한다.
    if (verdict === null) log.record("verdict_cleared", id);
    else log.record("verdict_set", id, { verdict });
    // 판정 취소는 옮기지 않는다 — 다시 고르려는 것이다.
    apply({ ...base, [id]: { verdict, missingObject } }, id, verdict !== null);
  };

  const link = (id: string, name: string) => {
    if (savingIdRef.current === id) return;
    const base = judgementsRef.current;
    const known = missingObjects(candidates, base,
                                 candidates.find((c) =>
                                   c.canonical_candidate_id === id)?.image ?? "");
    log.record(known.includes(name) ? "missing_object_linked"
                                    : "missing_object_created", id, { name });
    apply({
      ...base,
      [id]: { verdict: base[id]?.verdict ?? "hit", missingObject: name },
    }, id, true);
  };

  const retry = () => {
    const id = failedIdRef.current;
    if (id !== null && savingIdRef.current === id) return;
    const latest = judgementsRef.current;
    persist(latest, { id, advance: id !== null && latest[id]?.verdict != null, retry: true });
  };

  // 이동도 버튼과 단축키가 **같은 함수**를 부른다 — 기록(`moved_*`)이 갈리지 않게.
  // 묶음이 있으면 이전·다음은 **그 묶음 안에서만** 움직인다. 앞 묶음으로 돌아가 고치려면 묶음 단추를 쓴다.
  const canPrevious = cursor !== null && cursor > (span ? span.start : 0);
  const canNext = cursor !== null && cursor < (span ? span.end : candidates.length) - 1;
  // 옮기면 "저장됨"을 지운다 — 남겨 두면 아직 판정 안 한 다음 후보 아래에 "저장됨"이 떠서
  // 그 후보도 저장된 것처럼 읽힌다. 저장 중·실패는 그대로 둔다(실패는 다시 시도해야 한다).
  // 화면 표시만 바꾼다 — 저장 요청·기록은 건드리지 않는다.
  const moveTo = (index: number | null) => {
    setSave((s) => (s === "saved" || s === "advanced" ? "idle" : s));
    cursorRef.current = index;
    setBundleDone(null);
    setCursor(index);
  };
  /** 묶음의 첫 미판정으로, 다 판정한 묶음이면 그 묶음의 첫 후보로. */
  const entryOf = (s: BundleSpan) =>
    nextUnjudgedInSpan(candidates, judgements, s.start - 1, s) ?? s.start;
  /**
   * 묶음 이동. 앞 묶음(고치러 돌아가기)과 미판정이 남은 가장 앞 묶음까지만 갈 수 있다 — 묶음을 건너뛰어
   * 앞질러 판정하지 않는다(묶음 순서대로). 기록은 기존 이벤트 `moved_previous`/`moved_next`에 묶음
   * 자리를 붙여 남긴다.
   */
  const goBundle = (target: BundleSpan, meta: Record<string, unknown>) => {
    const from = span?.index ?? bundleDone ?? -1;
    log.record(target.index < from ? "moved_previous" : "moved_next", null, meta);
    moveTo(entryOf(target));
  };
  const reachable = (s: BundleSpan) => upcoming === null || s.index <= upcoming.index;
  // "다음 미판정" — 묶음이 있으면 지금 묶음 안에서만(묶음 완료 화면에서는 다음 묶음의 첫 미판정).
  const spanLeft = span ? span.size - judgedInSpan(candidates, judgements, span) : left;
  const nextUnjudgedTarget = () => {
    if (!spans) return nextUnjudgedIndex(candidates, judgements, cursor ?? -1);
    if (span) return nextUnjudgedInSpan(candidates, judgements, cursor ?? span.start - 1, span);
    return resumeIndex(candidates, judgements, spans);
  };
  const goPrevious = () => {
    log.record("moved_previous");
    moveTo((cursor ?? 0) - 1);
  };
  const goNext = () => {
    log.record("moved_next");
    moveTo((cursor ?? 0) + 1);
  };

  /**
   * 단축키 — 1 오류 있음 · 2 오류 없음 · 3 판단 보류 · ←/→ 이전/다음.
   *
   * **클릭과 같은 `judge`를 부른다.** 그래야 `verdict_set`·저장 기록이 클릭과 똑같다. 입력칸에서
   * 글자를 칠 때, 튜토리얼이 떠 있을 때, 키를 누르고 있어 반복될 때는 아무것도 하지 않는다 —
   * 반복 입력은 같은 판정을 여러 번 저장하고 기록한다.
   */
  const keyRef = useRef<(e: KeyboardEvent) => void>(() => undefined);
  keyRef.current = (e: KeyboardEvent) => {
    if (tutorial || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
    // 대화 상자(튜토리얼·전체 이미지 보기)가 떠 있으면 뒤 화면을 조작하지 않는다.
    if (document.querySelector('[aria-modal="true"]')) return;
    const el = e.target as HTMLElement | null;
    const tag = el?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return;

    if (e.key === "ArrowLeft" && canPrevious) {
      e.preventDefault();
      goPrevious();
      return;
    }
    if (e.key === "ArrowRight" && canNext) {
      e.preventDefault();
      goNext();
      return;
    }
    const verdict = KEY_VERDICT[e.key];
    if (verdict && current) {
      e.preventDefault();
      judge(current.canonical_candidate_id, verdict);
    }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => keyRef.current(e);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (error) return <p className="error">{error}</p>;

  // 저장 칸이 비어 있을 때의 안내. 판정 결과는 말하지 않고 "저장되는지"만 말한다.
  const currentId = current?.canonical_candidate_id;
  const idleHint = !currentId || blocked.includes(currentId)
    ? ""
    : judgements[currentId]?.verdict
      ? "이 후보의 판정은 저장되어 있습니다."
      : "판정을 누르면 바로 저장되고 다음 후보로 넘어갑니다.";
  const saveText = save === "idle" ? idleHint : saveMessage(save);

  return (
    <section className="blind-adjudication">
      {tutorial && <BlindTutorial onClose={closeTutorial} />}
      {/* 튜토리얼이 떠 있으면 뒤 화면을 `inert`로 막는다 — Tab으로 뒤의 판정 단추에 닿아
          Enter·Space로 판정이 눌리지 않게(단축키 1·2·3은 이미 막혀 있다). */}
      <div className="judge-body" inert={tutorial}>
      <div className="judge-header">
        <h2>가림 판정</h2>
        <button type="button" className="judge-text-button" onClick={() => setTutorial(true)}>
          튜토리얼 다시 보기
        </button>
      </div>
      {/* **머리글을 짧게 둔다.** 후보마다 스크롤해야 버튼이 보이면 시간이
          늘고 엉뚱한 버튼을 누른다. 자세한 설명은 화면 아래에 있다. */}
      <p className="muted">방법·점수·원래 순위·세부 의심 유형을 가립니다.</p>
      {/* 접어 둔다 — 펼쳐 두면 후보마다 버튼까지 스크롤이 길어진다(위 주석). */}
      <details className="guide-details">
        <summary>판정 지침 보기</summary>
        <JudgingGuideline />
      </details>

      {damaged && <p className="warn" role="alert">{DAMAGED_MESSAGE}</p>}
      {conflict && <p className="error" role="alert">{HASH_CONFLICT_MESSAGE}</p>}

      {/* 남은 수는 진행 상황이지 판정 결과 요약이 아니다 — 유형별 개수는 띄우지 않는다. */}
      <div className="judge-progress">
        <progress
          value={stats.judged}
          max={Math.max(stats.total, 1)}
          aria-label="판정 진행"
        />
        <span>
          {stats.judged} / {stats.total} 판정 (남은 {stats.left})
        </span>
      </div>

      {/* 묶음(사전 등록 D5·D6). 층과 묶음 안 진행만 보인다 — 방법·점수·출처·표본 여부는 묶음과 무관하다. */}
      {spans && (
        <nav className="judge-bundles" aria-label="묶음 이동">
          {spans.map((s) => (
            <button
              key={s.index}
              type="button"
              className="judge-chip judge-bundle-chip"
              aria-current={span?.index === s.index ? "step" : undefined}
              disabled={!reachable(s) || span?.index === s.index}
              onClick={() => goBundle(s, { bundle: s.index })}
            >
              {bundleLabel(s)} ({judgedInSpan(candidates, judgements, s)}/{s.size})
            </button>
          ))}
        </nav>
      )}

      {loading && <p>불러오는 중…</p>}

      {current && (
        <article key={current.canonical_candidate_id} className="judge-card">
          {/* 위치는 섞인 순서의 몇 번째인지일 뿐이다(서버가 고정 씨앗으로 섞는다) — 원래 순위가 아니다. */}
          <p className="judge-meta">
            <span className="judge-position">
              {span ? bundleHeader(span, cursor ?? 0) : `후보 ${(cursor ?? 0) + 1} / ${candidates.length}`}
            </span>
            <span>{current.image}</span>
          </p>
          <div className="judge-split">
          <AdjudicationView
            className="judge-figure"
            datasetId={datasetId}
            image={current.image}
            box={current.box}
            labelIndex={current.label_index}
          />
          <div className="judge-controls">
          <p className="judge-question">{questionFor(current.label_index)}</p>
          <p className="muted judge-help">
            {current.label_index === null
              ? "실제 객체가 있는데 라벨(파랑)이 없으면 오류 있음, 객체가 아니거나 라벨 대상이 아니거나 이미 파랑이 덮고 있으면 오류 없음, 가림·해상도 때문에 불명확하면 판단 보류."
              : "고쳐야 할 만큼 어긋났으면 오류 있음, 이대로 학습에 써도 되면 오류 없음, 경계가 애매하거나 객체를 확인할 수 없으면 판단 보류."}
          </p>

          {/* 단축키 표시는 CSS(`data-key`)로 그린다 — 버튼의 접근 이름과 글자는 판정 이름만 남는다. */}
          <div className="verdict-row">
            {VERDICTS.map(({ verdict: v, label, key }) => (
              <button
                key={v}
                type="button"
                className={`verdict-button verdict-${v}`}
                data-key={key}
                aria-keyshortcuts={key}
                aria-pressed={judgements[current.canonical_candidate_id]?.verdict === v}
                onClick={() => judge(current.canonical_candidate_id, v)}
              >
                {label}
              </button>
            ))}
          </div>
          {/* 저장 상태는 **판정 단추 바로 아래 고정 높이 줄**에 둔다 — 단추 가까이 있어 찾으러
              가지 않고, 문구가 생겨도 단추가 밀리지 않는다(브라우저 확인에서 밀린 단추를 잘못
              누른 적이 있다). */}
          <div className="save-row">
            <button
              type="button"
              className="judge-text-button"
              onClick={() => judge(current.canonical_candidate_id, null)}
            >
              판정 취소
            </button>
            <p aria-live="polite" className={`save-status save-${save}`}>{saveText}</p>
            {save === "failed" && (
              <button type="button" className="judge-nav-button" onClick={retry}>
                다시 시도
              </button>
            )}
          </div>

          {current.label_index === null &&
            judgements[current.canonical_candidate_id]?.verdict === "hit" && (
              <fieldset className="missing-object">
                <legend>어느 객체인가</legend>
                <p className="missing-hint">
                  이 사진에서 이미 번호를 붙인 차와 <b>같은 차</b>면 그 번호를, 처음 보는 차면
                  <b> 새 객체</b>를 고릅니다. 골라야 저장되고, 저장되면 다음 후보로 넘어갑니다.
                </p>
                {missingObjects(candidates, judgements, current.image).map((name) => (
                  <button
                    key={name}
                    type="button"
                    className="judge-chip"
                    aria-pressed={
                      judgements[current.canonical_candidate_id]?.missingObject === name
                    }
                    onClick={() => link(current.canonical_candidate_id, name)}
                  >
                    {name}
                  </button>
                ))}
                <button
                  type="button"
                  className="judge-chip judge-chip-new"
                  onClick={() =>
                    link(
                      current.canonical_candidate_id,
                      nextMissingObject(candidates, judgements, current.image),
                    )
                  }
                >
                  새 객체
                </button>
              </fieldset>
            )}
          </div>
          </div>
        </article>
      )}

      {/* 저장 상태와 경고는 **판정 버튼 아래**에 둔다. 위에 두면 판정할 때마다
          문구가 생겨 버튼이 밀리고, 연달아 누르는 사람이 엉뚱한 버튼을 누른다
          — 실제로 브라우저 확인에서 그렇게 눌렸다. */}
      {/* 묶음 완료 화면 — 쉬어도 되는 자리. 다음 묶음은 판정자가 눌러야 시작한다. */}
      {bundleBreak && finishedSpan && upcoming && (
        <div className="done bundle-done" role="status">
          <p>{bundleCompleteMessage(finishedSpan)}</p>
          {upcoming.layer === LAYER_MISSING && finishedSpan.layer !== LAYER_MISSING && (
            <p className="muted">
              다음은 누락 묶음입니다 — 질문이 &ldquo;{questionFor(null)}&rdquo;로 바뀝니다.
            </p>
          )}
          <button
            type="button"
            className="judge-nav-button"
            onClick={() => goBundle(upcoming, { bundle_start: upcoming.index })}
          >
            다음 묶음 시작 — {bundleLabel(upcoming)}
          </button>
        </div>
      )}

      {done && (
        <p className="done" role="status">
          {ALL_JUDGED_MESSAGE}{" "}
          <button
            type="button"
            className="judge-nav-button"
            onClick={() => {
              // **되돌아보는 것은 의도한 작업이다.** 그 시간은 그 후보의
              // 판정 시간으로 기록된다 — 재개 시의 통과 시간과 다르다.
              log.record("moved_previous");
              moveTo(0);
            }}
          >
            처음부터 다시 보기
          </button>
        </p>
      )}

      <nav className="judge-nav">
        <button
          type="button"
          className="judge-nav-button"
          data-key="←"
          aria-keyshortcuts="ArrowLeft"
          disabled={!canPrevious}
          onClick={goPrevious}
        >
          이전
        </button>
        <button
          type="button"
          className="judge-nav-button"
          data-key="→"
          aria-keyshortcuts="ArrowRight"
          disabled={!canNext}
          onClick={goNext}
        >
          다음
        </button>
        <button
          type="button"
          className="judge-nav-button"
          disabled={spanLeft === 0}
          onClick={() => {
            log.record("moved_next");
            moveTo(nextUnjudgedTarget());
          }}
        >
          다음 미판정 ({spanLeft})
        </button>
      </nav>

      {blocked.length > 0 && (
        <p className="warn" role="alert">
          {MISSING_NEEDS_OBJECT} <strong>아직 저장되지 않은 판정 {blocked.length}건</strong>
        </p>
      )}
      {/* 후보가 없는 화면(완료·불러오는 중)에서도 저장 실패는 보여야 다시 시도할 수 있다. */}
      {!current && save === "failed" && (
        <div className="save-row">
          <p aria-live="polite" className="save-status save-failed">{saveMessage(save)}</p>
          <button type="button" className="judge-nav-button" onClick={retry}>
            다시 시도
          </button>
        </div>
      )}

      <p className="muted judge-footnote">
        <strong>기존 라벨 검수인지 누락 객체 검수인지는 가리지 않습니다</strong>{" "}
        — 판정 작업 자체가 달라 숨기면 판정할 수 없습니다.{" "}
        <strong>판정은 판정자마다 따로 저장되고, 다른 판정자의 판정은 보이지 않습니다.</strong>
      </p>
      </div>
    </section>
  );
}
