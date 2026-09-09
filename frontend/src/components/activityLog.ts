/**
 * 판정 작업 기록 (docs/pilot-evaluation-plan.md).
 *
 * **"페이지를 열어 둔 시간"은 검수 시간이 아니다.** 그래서 화면은 무슨 일이
 * 언제 일어났는지만 남기고, **계산은 하지 않는다.**
 *
 * 계산을 화면에서 하면 두 가지가 나빠진다. 그 숫자가 화면에 뜨기 쉬워지고
 * (판정자가 보면 서두른다), 나중에 규칙을 고쳐도 이미 저장된 기록을 다시
 * 계산할 수 없다. 계산은 `experiment/evaluation/activity.py`가 한다.
 *
 * **기록이 유실되면 그 시간은 영영 없다.** 판정은 다시 누를 수 있지만 "언제
 * 눌렀는가"는 다시 만들 수 없다. 그래서 보내지 못한 것을 브라우저에 남겨 두고
 * 다음에 **같은 `event_id`로** 다시 보낸다.
 */

// 서버의 `EVENT_SCHEMA_VERSION`과 같은 값이다.
export const EVENT_SCHEMA_VERSION = 1;

export type ActivityEvent = {
  /** 이벤트마다 영구히 고유. **재전송해도 안 바뀐다.** */
  event_id: string;
  session_id: string;
  /** 세션 안에서 0부터 하나씩. 구멍이 나면 전송이 유실된 것이다. */
  sequence: number;
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

/** 서버가 받아 주는 id 모양. 영숫자와 `_-`만. */
export function newId(prefix = ""): string {
  const random = Math.random().toString(36).slice(2, 10);
  return `${prefix}${Date.now().toString(36)}-${random}`;
}

/**
 * 보내지 못한 기록을 어디에 두는가.
 *
 * **평가마다 따로 둔다.** 한 키에 모으면 다른 평가의 이벤트가 섞여, 묶음 해시가
 * 안 맞아 통째로 거부당한다.
 */
export function queueKey(datasetId: string, evaluationId: string): string {
  return `aida.activity.${datasetId}.${evaluationId}`;
}

function readQueue(key: string): ActivityEvent[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    // 저장소를 못 읽어도 판정은 이어져야 한다.
    return [];
  }
}

function writeQueue(key: string, events: ActivityEvent[]): void {
  try {
    if (events.length === 0) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(events));
  } catch {
    // 용량이 찼거나 사생활 보호 모드다. 기록을 잃을 뿐 판정은 이어진다.
  }
}

export type SendResult = { acknowledged?: string[] } | void;

/**
 * 이벤트를 모았다가 한 번에 보낸다.
 *
 * 하나씩 보내면 판정 한 번에 요청이 서너 개씩 나가 **저장 요청과 뒤엉킨다.**
 * 기록은 지난 일이라 조금 늦게 도착해도 되고, 이어붙이기라 순서만 지키면 된다.
 *
 * **기록 전송이 실패해도 판정을 막지 않는다.** 판정이 이 제품의 일이고
 * 기록은 우리가 재려고 붙인 것이다 — 재는 쪽이 하는 일을 멈추면 안 된다.
 *
 * 실패한 묶음은 **브라우저에 남겨** 다음 접속 때 같은 `event_id`로 다시
 * 보낸다. 서버가 **확인해 준 것만** 지운다 — 응답을 못 받았는데 지우면 그
 * 시간이 영영 사라지고, 서버가 이미 저장했는데 다시 보내도 `event_id`로
 * 걸러진다.
 */
export function makeActivityLogger(
  send: (events: ActivityEvent[]) => Promise<SendResult>,
  {
    flushEvery = 12,
    storageKey = "",
    sessionId = newId("s"),
  }: { flushEvery?: number; storageKey?: string; sessionId?: string } = {},
) {
  // 지난 접속에서 못 보낸 것부터 이어받는다.
  let queued: ActivityEvent[] = storageKey ? readQueue(storageKey) : [];
  let sending = false;
  let sequence = 0;

  const persist = () => {
    if (storageKey) writeQueue(storageKey, queued);
  };

  const flush = async (): Promise<boolean> => {
    if (sending || queued.length === 0) return true;
    sending = true;
    const batch = queued.slice();
    try {
      const result = await send(batch);
      const acknowledged = new Set(
        (result && "acknowledged" in result && result.acknowledged) ||
          batch.map((e) => e.event_id),
      );
      // **확인받은 것만 지운다.** 그 사이에 쌓인 것은 그대로 남는다.
      queued = queued.filter((e) => !acknowledged.has(e.event_id));
      persist();
      return true;
    } catch {
      persist();
      return false;
    } finally {
      sending = false;
    }
  };

  return {
    get sessionId() {
      return sessionId;
    },
    record(event: string, candidateId: string | null = null,
           meta: Record<string, unknown> = {}) {
      queued.push({
        event_id: newId("e"),
        session_id: sessionId,
        sequence: sequence++,
        event,
        canonical_candidate_id: candidateId,
        ...now(),
        meta,
      });
      persist();
      if (queued.length >= flushEvery) void flush();
    },
    /** 지금까지 모인 것을 보낸다. 실패하면 `false`이고 큐에 남는다. */
    flush,
    /**
     * **창이 닫히는 중에 보낸다.**
     *
     * 이때는 보통의 요청이 취소된다 — 브라우저가 페이지를 버리면서 진행 중인
     * fetch도 같이 버린다. `sendBeacon`은 문서가 사라진 뒤에도 브라우저가
     * 마저 보내 준다.
     *
     * **성공을 확인할 수 없다.** 응답을 못 받으므로 큐에서 지우지 않는다 —
     * 서버가 이미 받았다면 다음 접속의 재전송이 `event_id`로 걸러진다.
     */
    flushOnExit(url: string, body: (events: ActivityEvent[]) => unknown): boolean {
      if (queued.length === 0) return true;
      try {
        const blob = new Blob([JSON.stringify(body(queued))],
                              { type: "application/json" });
        return navigator.sendBeacon(url, blob);
      } catch {
        return false;
      }
    },
    get pending() {
      return queued.length;
    },
    get nextSequence() {
      return sequence;
    },
  };
}
