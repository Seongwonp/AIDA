/**
 * 판정 작업 기록 (docs/pilot-evaluation-plan.md).
 *
 * **"페이지를 열어 둔 시간"은 검수 시간이 아니다.** 그래서 화면은 무슨 일이
 * 언제 일어났는지만 남기고, **계산은 하지 않는다.**
 *
 * 계산을 화면에서 하면 두 가지가 나빠진다. 그 숫자가 화면에 뜨기 쉬워지고
 * (판정자가 보면 서두른다), 나중에 규칙을 고쳐도 이미 저장된 기록을 다시
 * 계산할 수 없다. 계산은 `experiment/evaluation/activity.py`가 한다.
 */

// 서버의 `EVENT_SCHEMA_VERSION`과 같은 값이다.
export const EVENT_SCHEMA_VERSION = 1;

export type ActivityEvent = {
  session_id: string;
  event: string;
  canonical_candidate_id: string | null;
  /** UTC 벽시계. **언제 일어났는지**를 말한다. */
  at: string;
  /** 세션 안에서만 유효한 단조 증가 시간. **길이는 이것으로만 잰다.** */
  elapsed_ms: number;
  meta: Record<string, unknown>;
};

/**
 * 벽시계와 단조 시계를 **둘 다** 남긴다.
 *
 * 벽시계는 자정을 넘거나 시스템 시계가 바뀌면 **뒤로 갈 수 있다.** 그걸로
 * 길이를 재면 음수가 나온다. 단조 시계(`performance.now()`)는 뒤로 안 가지만
 * 페이지가 새로 뜨면 0부터라, 언제인지는 못 말한다. 그래서 둘 다 남긴다.
 */
export function now(): { at: string; elapsed_ms: number } {
  return {
    at: new Date().toISOString(),
    elapsed_ms: Math.max(0, Math.round(performance.now())),
  };
}

/** 세션 하나의 이름. **새로고침하면 새 세션이다.** */
export function newSessionId(): string {
  const random = Math.random().toString(36).slice(2, 10);
  return `${Date.now().toString(36)}-${random}`;
}

/**
 * 이벤트를 모았다가 한 번에 보낸다.
 *
 * 하나씩 보내면 판정 한 번에 요청이 서너 개씩 나가 **저장 요청과 뒤엉킨다.**
 * 기록은 지난 일이라 조금 늦게 도착해도 되고, 이어붙이기라 순서만 지키면 된다.
 *
 * **기록 전송이 실패해도 판정을 막지 않는다.** 판정이 이 제품의 일이고
 * 기록은 우리가 재려고 붙인 것이다 — 재는 쪽이 하는 일을 멈추면 안 된다.
 * 대신 실패한 묶음은 다시 큐에 넣어 다음에 같이 보낸다.
 */
export function makeActivityLogger(
  send: (events: ActivityEvent[]) => Promise<unknown>,
  { flushEvery = 12 }: { flushEvery?: number } = {},
) {
  let queued: ActivityEvent[] = [];
  let sending = false;
  let sessionId = newSessionId();

  const flush = async (): Promise<boolean> => {
    if (sending || queued.length === 0) return true;
    sending = true;
    const batch = queued;
    queued = [];
    try {
      await send(batch);
      return true;
    } catch {
      // 앞에 되돌려 놓는다 — 순서가 뒤집히면 시간 계산이 틀린다.
      queued = batch.concat(queued);
      return false;
    } finally {
      sending = false;
    }
  };

  return {
    get sessionId() {
      return sessionId;
    },
    /** 새로고침처럼 세션이 끊긴 자리. `elapsed_ms`가 0부터 다시 센다. */
    startSession() {
      sessionId = newSessionId();
    },
    record(event: string, candidateId: string | null = null,
           meta: Record<string, unknown> = {}) {
      queued.push({ session_id: sessionId, event,
                    canonical_candidate_id: candidateId, ...now(), meta });
      if (queued.length >= flushEvery) void flush();
    },
    /** 지금까지 모인 것을 보낸다. 실패하면 `false`이고 큐에 남는다. */
    flush,
    get pending() {
      return queued.length;
    },
  };
}
