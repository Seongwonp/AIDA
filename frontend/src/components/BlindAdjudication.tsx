import { useEffect, useMemo, useRef, useState } from "react";

import { getBlindQueue, postActivity, putAdjudications } from "../api";
import { makeActivityLogger, queueKey } from "./activityLog";
import { API_BASE_URL } from "../api";
import { AdjudicationView } from "./AdjudicationView";
import {
  ALL_JUDGED_MESSAGE,
  blockedIds,
  DAMAGED_MESSAGE,
  firstUnjudgedIndex,
  nextUnjudgedIndex,
  HASH_CONFLICT_MESSAGE,
  MISSING_NEEDS_OBJECT,
  makeAdjudicationSender,
  missingObjects,
  nextMissingObject,
  progress,
  saveMessage,
  toJudgements,
  toRequest,
  unjudgedCount,
  type BlindCandidate,
  type EvalVerdict,
  type Judgements,
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
  const [save, setSave] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  // `null`은 **띄울 후보가 없다**는 뜻이다 — 아직 안 불러왔거나 전부
  // 판정했거나. 0번으로 갈음하면 이미 판정한 후보에 시간이 쌓인다.
  const [cursor, setCursor] = useState<number | null>(null);
  // 후보를 화면에 띄운 순간. 후보별 시간은 여기서부터 잰다.
  const openedRef = useRef<string | null>(null);

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
    openedRef.current = null;
    setHash("");
    setError(null);
    setConflict(false);
    setDamaged(false);
    setSave("idle");

    // 목록을 기다린 시간은 **사람이 판정한 시간이 아니다.** 그 구간을 가려낼
    // 수 있게 조회의 시작과 끝을 남긴다.
    log.record("queue_load_started");
    getBlindQueue(datasetId, evaluationId)
      .then((data) => {
        if (cancelled) return;
        log.record("queue_load_succeeded");
        const restored = toJudgements(data.candidates);
        setCandidates(data.candidates);
        setHash(data.candidate_set_hash);
        setDamaged(data.damaged);
        setJudgements(restored);
        // **아직 판정 안 한 첫 후보에서 이어 한다.** 0번부터 시작하면 두 번째
        // 세션에서 이미 판정한 후보를 넘기는 시간이 그 후보들의 판정 시간에
        // 다시 쌓여, 후보당 시간이 부풀고 N이 작아진다.
        setCursor(firstUnjudgedIndex(data.candidates, restored));
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
  const done = !loading && candidates.length > 0 && cursor === null;

  const persist = (next: Judgements, retry = false) => {
    if (blockedIds(candidates, next).length > 0) {
      // 누락 hit인데 어느 객체인지 안 정했다. **보내지 않는다.**
      setSave("idle");
      return;
    }
    setSave("saving");
    if (retry) log.record("save_retried");
    log.record("save_started");
    void sendToServer(toRequest(candidates, next)).then((ok) => {
      log.record(ok ? "save_succeeded" : "save_failed");
      setSave(ok ? "saved" : "failed");
    });
  };

  // **상태 갱신 함수 안에서 저장하지 않는다.** 갱신 함수는 React가 두 번 부를
  // 수 있어(개발 모드의 StrictMode) 같은 판정이 두 번 나간다.
  const apply = (next: Judgements) => {
    setJudgements(next);
    persist(next);
  };

  const judge = (id: string, verdict: EvalVerdict | null) => {
    const before = judgements[id] ?? { verdict: null };
    // 오류가 아니라고 바꾸면 붙여 둔 누락 객체도 뗀다 — 남겨 두면 판정과
    // 이름이 어긋난 채로 저장된다.
    const missingObject = verdict === "hit" ? before.missingObject ?? null : null;
    // **판정 유형을 기록에 남긴다.** 화면에는 안 띄운다 — 요약이 뜨면
    // 판정자가 그걸 보고 다음 판단을 조절한다.
    if (verdict === null) log.record("verdict_cleared", id);
    else log.record("verdict_set", id, { verdict });
    apply({ ...judgements, [id]: { verdict, missingObject } });
  };

  const link = (id: string, name: string) => {
    const known = missingObjects(candidates, judgements,
                                 candidates.find((c) =>
                                   c.canonical_candidate_id === id)?.image ?? "");
    log.record(known.includes(name) ? "missing_object_linked"
                                    : "missing_object_created", id, { name });
    apply({
      ...judgements,
      [id]: { verdict: judgements[id]?.verdict ?? "hit", missingObject: name },
    });
  };

  const retry = () => persist(judgements, true);

  if (error) return <p className="error">{error}</p>;

  return (
    <section className="blind-adjudication">
      <h2>가림 판정</h2>
      {/* **머리글을 짧게 둔다.** 후보마다 스크롤해야 버튼이 보이면 시간이
          늘고 엉뚱한 버튼을 누른다. 자세한 설명은 화면 아래에 있다. */}
      <p className="muted">방법·점수·원래 순위·세부 의심 유형을 가립니다.</p>

      {damaged && <p className="warn" role="alert">{DAMAGED_MESSAGE}</p>}
      {conflict && <p className="error" role="alert">{HASH_CONFLICT_MESSAGE}</p>}

      <p>
        {stats.judged} / {stats.total} 판정 (남은 {stats.left})
      </p>

      {loading && <p>불러오는 중…</p>}

      {current && (
        <article key={current.canonical_candidate_id}>
          <p>{current.image}</p>
          <AdjudicationView
            datasetId={datasetId}
            image={current.image}
            box={current.box}
            labelIndex={current.label_index}
          />
          <p>
            {current.label_index === null
              ? `여기 ${current.class_name ?? "객체"}가 있는데 라벨이 빠졌는가?`
              : `이 ${current.class_name ?? "객체"} 라벨이 잘 감쌌는가?`}
          </p>
          <p className="muted">
            {current.label_index === null
              ? "실제 객체가 있는데 라벨이 없으면 오류였다, 객체가 아니거나 라벨 대상이 아니면 오류 아니었다, 가림·해상도 때문에 불명확하면 모르겠다."
              : "실무상 고쳐야 할 만큼 어긋났으면 오류였다, 이대로 써도 되면 오류 아니었다, 경계가 애매하거나 객체를 확인할 수 없으면 모르겠다."}
          </p>

          {(["hit", "miss", "hold"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={judgements[current.canonical_candidate_id]?.verdict === v}
              onClick={() => judge(current.canonical_candidate_id, v)}
            >
              {v === "hit" ? "오류였다" : v === "miss" ? "오류 아니었다" : "모르겠다"}
            </button>
          ))}
          <button type="button" onClick={() => judge(current.canonical_candidate_id, null)}>
            판정 취소
          </button>

          {current.label_index === null &&
            judgements[current.canonical_candidate_id]?.verdict === "hit" && (
              <fieldset>
                <legend>어느 객체인가</legend>
                {missingObjects(candidates, judgements, current.image).map((name) => (
                  <button
                    key={name}
                    type="button"
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
        </article>
      )}

      {/* 저장 상태와 경고는 **판정 버튼 아래**에 둔다. 위에 두면 판정할 때마다
          문구가 생겨 버튼이 밀리고, 연달아 누르는 사람이 엉뚱한 버튼을 누른다
          — 실제로 브라우저 확인에서 그렇게 눌렸다. */}
      {done && (
        <p className="done" role="status">
          {ALL_JUDGED_MESSAGE}{" "}
          <button
            type="button"
            onClick={() => {
              // **되돌아보는 것은 의도한 작업이다.** 그 시간은 그 후보의
              // 판정 시간으로 기록된다 — 재개 시의 통과 시간과 다르다.
              log.record("moved_previous");
              setCursor(0);
            }}
          >
            처음부터 다시 보기
          </button>
        </p>
      )}

      <nav>
        <button
          type="button"
          disabled={cursor === null || cursor === 0}
          onClick={() => {
            log.record("moved_previous");
            setCursor((cursor ?? 0) - 1);
          }}
        >
          이전
        </button>
        <button
          type="button"
          disabled={cursor === null || cursor >= candidates.length - 1}
          onClick={() => {
            log.record("moved_next");
            setCursor((cursor ?? 0) + 1);
          }}
        >
          다음
        </button>
        <button
          type="button"
          disabled={left === 0}
          onClick={() => {
            log.record("moved_next");
            setCursor(nextUnjudgedIndex(candidates, judgements, cursor ?? -1));
          }}
        >
          다음 미판정 ({left})
        </button>
      </nav>

      <p className="muted">
        <strong>기존 라벨 검수인지 누락 객체 검수인지는 가리지 않습니다</strong>{" "}
        — 판정 작업 자체가 달라 숨기면 판정할 수 없습니다.{" "}
        <strong>판정자는 아직 개발자이며, 독립된 판정이 아닙니다.</strong>
      </p>

      {blocked.length > 0 && (
        <p className="warn" role="alert">
          {MISSING_NEEDS_OBJECT} <strong>아직 저장되지 않은 판정 {blocked.length}건</strong>
        </p>
      )}
      <p aria-live="polite">{saveMessage(save)}</p>
      {save === "failed" && (
        <button type="button" onClick={retry}>
          다시 시도
        </button>
      )}
    </section>
  );
}
