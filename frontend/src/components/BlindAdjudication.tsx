import { useEffect, useMemo, useRef, useState } from "react";

import { getBlindQueue, postActivity, putAdjudications } from "../api";
import { makeActivityLogger } from "./activityLog";
import { BoxPreview } from "./BoxPreview";
import {
  blockedIds,
  DAMAGED_MESSAGE,
  HASH_CONFLICT_MESSAGE,
  MISSING_NEEDS_OBJECT,
  makeAdjudicationSender,
  missingObjects,
  nextMissingObject,
  progress,
  saveMessage,
  toJudgements,
  toRequest,
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
  const [cursor, setCursor] = useState(0);

  // 작업 기록. **계산은 여기서 안 한다** — 무슨 일이 언제 있었는지만 남기고,
  // 시간 계산은 `experiment/evaluation/activity.py`가 나중에 한다
  // (docs/pilot-evaluation-plan.md).
  const hashRef = useRef("");
  hashRef.current = hash;
  const log = useMemo(
    () =>
      makeActivityLogger((events) =>
        postActivity(datasetId, evaluationId, hashRef.current, events),
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
    setCursor(0);
    setHash("");
    setError(null);
    setConflict(false);
    setDamaged(false);
    setSave("idle");

    getBlindQueue(datasetId, evaluationId)
      .then((data) => {
        if (cancelled) return;
        setCandidates(data.candidates);
        setHash(data.candidate_set_hash);
        setDamaged(data.damaged);
        setJudgements(toJudgements(data.candidates));
      })
      .catch(() => {
        if (!cancelled) setError("판정 목록을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [datasetId, evaluationId]);

  useEffect(() => {
    // **여기서 새 세션을 시작하지 않는다.** 세션은 logger를 만들 때 하나
    // 생기고, 그건 페이지 한 번 뜰 때 한 번이다. effect마다 새로 시작하면
    // 개발 모드의 StrictMode가 effect를 두 번 돌려 **세션 수가 두 배로**
    // 잡힌다 — dry pilot에서 2회 방문이 4세션으로 나와 잡혔다.
    log.record("session_started");

    const onVisibility = () =>
      log.record("visibility_changed", null,
                 { visible: document.visibilityState === "visible" });
    const onFocus = () => log.record("focus_changed", null, { focused: true });
    const onBlur = () => log.record("focus_changed", null, { focused: false });
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);

    // 기록을 주기적으로 보낸다. 판정 흐름과 엮지 않는다 — 기록 전송이
    // 실패해도 판정은 이어져야 한다.
    const timer = window.setInterval(() => void log.flush(), 10_000);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
      window.clearInterval(timer);
      log.record("session_ended");
      void log.flush();
    };
  }, [log]);

  // 후보를 화면에 띄운 순간. 후보별 시간은 여기서부터 잰다.
  const openedRef = useRef<string | null>(null);
  useEffect(() => {
    const id = candidates[cursor]?.canonical_candidate_id ?? null;
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
  const current = candidates[cursor];

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
      <p className="muted">
        방법·점수·원래 순위·세부 의심 유형을 가린 채 판정합니다.{" "}
        <strong>기존 라벨 검수인지 누락 객체 검수인지는 가리지 않습니다</strong>{" "}
        — 판정 작업 자체가 달라 숨기면 판정할 수 없습니다.
      </p>
      <p className="muted">
        <strong>판정자는 아직 개발자이며, 독립된 판정이 아닙니다.</strong>
      </p>

      {damaged && <p className="warn" role="alert">{DAMAGED_MESSAGE}</p>}
      {conflict && <p className="error" role="alert">{HASH_CONFLICT_MESSAGE}</p>}

      <p>
        {stats.judged} / {stats.total} 판정 (남은 {stats.left})
      </p>

      {loading && <p>불러오는 중…</p>}

      {current && (
        <article key={current.canonical_candidate_id}>
          <p>{current.image}</p>
          {current.box && (
            <BoxPreview datasetId={datasetId} image={current.image} box={current.box} />
          )}
          <p>
            {current.label_index === null
              ? "라벨이 없는 자리 — 빠진 객체인가?"
              : `${current.label_index}번 라벨 — 이 라벨이 틀렸는가?`}
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
      <nav>
        <button
          type="button"
          disabled={cursor === 0}
          onClick={() => {
            log.record("moved_previous");
            setCursor(cursor - 1);
          }}
        >
          이전
        </button>
        <button
          type="button"
          disabled={cursor >= candidates.length - 1}
          onClick={() => {
            log.record("moved_next");
            setCursor(cursor + 1);
          }}
        >
          다음
        </button>
      </nav>

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
