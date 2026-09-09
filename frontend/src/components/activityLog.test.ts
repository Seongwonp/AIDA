/**
 * 작업 기록의 규칙 (docs/pilot-evaluation-plan.md).
 *
 * 여기서 고정하는 것은 **화면이 무엇을 남기고 어떻게 잃지 않는가**다. 시간
 * 계산은 화면이 하지 않는다 — `experiment/evaluation/activity.py`가 나중에 한다.
 *
 * **기록이 유실되면 그 시간은 영영 없다.** 판정은 다시 누를 수 있지만 "언제
 * 눌렀는가"는 다시 만들 수 없다.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  makeActivityLogger,
  newId,
  now,
  queueKey,
  type ActivityEvent,
  type SendResult,
} from "./activityLog";

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

describe("시각", () => {
  test("벽시계와 단조 시계를 둘 다 남긴다", () => {
    // 벽시계는 자정을 넘거나 시스템 시계가 바뀌면 뒤로 갈 수 있어 길이를 못
    // 잰다. 단조 시계는 새로 뜨면 0부터라 언제인지를 못 말한다.
    const got = now();
    expect(got.at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(got.elapsed_ms).toBeGreaterThanOrEqual(0);
  });

  test("단조 시계는 음수가 되지 않는다", () => {
    const spy = vi.spyOn(performance, "now").mockReturnValue(-5);
    expect(now().elapsed_ms).toBe(0);
    spy.mockRestore();
  });
});

describe("이벤트 이름표", () => {
  test("id는 매번 다르고 서버가 받는 모양이다", () => {
    const one = newId("e");
    expect(one).not.toBe(newId("e"));
    // 서버는 영숫자와 _- 만 받는다.
    expect(one).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  });

  test("순번은 세션 안에서 0부터 하나씩 늘어난다", () => {
    // 구멍이 나면 전송이 유실된 것이다 — 집계가 그걸로 완전성을 판단한다.
    const log = makeActivityLogger(vi.fn().mockResolvedValue({}));
    log.record("a");
    log.record("b");
    log.record("c");
    expect(log.nextSequence).toBe(3);
  });

  test("남긴 것에 세션·순번·시각·후보가 들어간다", async () => {
    const send = vi.fn().mockResolvedValue({});
    const log = makeActivityLogger(send);
    log.record("verdict_set", "L123", { verdict: "hit" });
    await log.flush();

    const [batch] = send.mock.calls[0];
    expect(batch[0]).toMatchObject({
      event: "verdict_set",
      canonical_candidate_id: "L123",
      session_id: log.sessionId,
      sequence: 0,
      meta: { verdict: "hit" },
    });
    expect(batch[0].event_id).toBeTruthy();
    expect(batch[0].at).toBeTruthy();
  });
});

describe("모았다 보내기", () => {
  test("문턱에 닿기 전에는 안 보낸다", () => {
    // 하나씩 보내면 판정 한 번에 요청이 서너 개씩 나가 저장 요청과 뒤엉킨다.
    const send = vi.fn().mockResolvedValue({});
    const log = makeActivityLogger(send, { flushEvery: 3 });

    log.record("moved_next");
    log.record("moved_next");
    expect(send).not.toHaveBeenCalled();
    expect(log.pending).toBe(2);

    log.record("moved_next");
    expect(send).toHaveBeenCalledTimes(1);
  });

  test("보낼 것이 없으면 아무것도 안 보낸다", async () => {
    const send = vi.fn().mockResolvedValue({});
    await makeActivityLogger(send).flush();
    expect(send).not.toHaveBeenCalled();
  });

  test("보내는 중에는 겹쳐 보내지 않는다", async () => {
    let release!: () => void;
    const send = vi.fn(() => new Promise<void>((r) => (release = r)));
    const log = makeActivityLogger(send);

    log.record("a");
    const first = log.flush();
    log.record("b");
    void log.flush();
    expect(send).toHaveBeenCalledTimes(1);

    release();
    await first;
    expect(log.pending).toBe(1);         // b는 아직 큐에 있다
  });

  test("보내는 사이에 쌓인 것은 안 지운다", async () => {
    // 응답이 확인해 준 것만 지운다. 그 사이의 입력까지 지우면 그 시간이 사라진다.
    let release!: (v: SendResult) => void;
    const send = vi.fn(() => new Promise<SendResult>((r) => (release = r)));
    const log = makeActivityLogger(send);

    log.record("first");
    const flushing = log.flush();
    log.record("second");

    release({});
    await flushing;
    expect(log.pending).toBe(1);
  });
});

describe("잃지 않기", () => {
  test("실패하면 큐에 남고 다음에 같이 보낸다", async () => {
    // 판정이 이 제품의 일이고 기록은 우리가 재려고 붙인 것이다 — 재는 쪽이
    // 하는 일을 멈추면 안 된다.
    const send = vi.fn()
      .mockRejectedValueOnce(new Error("끊김"))
      .mockResolvedValue({});
    const log = makeActivityLogger(send);

    log.record("session_started");
    expect(await log.flush()).toBe(false);
    expect(log.pending).toBe(1);

    log.record("moved_next");
    expect(await log.flush()).toBe(true);

    const [batch] = send.mock.calls[1];
    // **순서가 뒤집히면 시간 계산이 틀린다.**
    expect(batch.map((e: ActivityEvent) => e.event))
      .toEqual(["session_started", "moved_next"]);
  });

  test("재전송해도 event_id가 안 바뀐다", async () => {
    // 새 id를 만들면 서버가 중복을 못 가려내고 두 벌이 남는다.
    const send = vi.fn()
      .mockRejectedValueOnce(new Error("끊김"))
      .mockResolvedValue({});
    const log = makeActivityLogger(send);

    log.record("session_started");
    await log.flush();
    await log.flush();

    expect(send.mock.calls[0][0][0].event_id)
      .toBe(send.mock.calls[1][0][0].event_id);
  });

  test("서버가 확인해 준 것만 지운다", async () => {
    // 응답을 못 받았는데 지우면 그 시간이 영영 사라진다.
    const send = vi.fn().mockResolvedValue({ acknowledged: [] });
    const log = makeActivityLogger(send);

    log.record("session_started");
    await log.flush();
    expect(log.pending).toBe(1);
  });

  test("서버가 이미 저장했다고 하면 지운다", async () => {
    // 응답만 못 받은 경우다. 계속 들고 있으면 영영 다시 보낸다.
    const send = vi.fn(async (events: ActivityEvent[]) => ({
      acknowledged: events.map((e) => e.event_id),
    }));
    const log = makeActivityLogger(send);

    log.record("session_started");
    await log.flush();
    expect(log.pending).toBe(0);
  });
});

describe("브라우저에 남겨 두기", () => {
  const KEY = queueKey("ds1", "e1");

  test("평가마다 다른 자리에 둔다", () => {
    // 한 키에 모으면 다른 평가의 이벤트가 섞여 묶음 해시가 안 맞아 통째로
    // 거부당한다.
    expect(queueKey("ds1", "e1")).not.toBe(queueKey("ds1", "e2"));
    expect(queueKey("ds1", "e1")).not.toBe(queueKey("ds2", "e1"));
  });

  test("못 보낸 것을 다음 접속에서 이어받는다", async () => {
    const failing = makeActivityLogger(
      vi.fn().mockRejectedValue(new Error("끊김")), { storageKey: KEY });
    failing.record("session_started");
    await failing.flush();

    // 새로고침 — 새 logger가 같은 자리를 읽는다.
    const send = vi.fn().mockResolvedValue({});
    const revived = makeActivityLogger(send, { storageKey: KEY });
    expect(revived.pending).toBe(1);

    await revived.flush();
    expect(send.mock.calls[0][0][0].event).toBe("session_started");
  });

  test("보낸 것은 자리에서 지운다", async () => {
    const log = makeActivityLogger(vi.fn().mockResolvedValue({}),
                                   { storageKey: KEY });
    log.record("session_started");
    await log.flush();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  test("저장소를 못 써도 판정은 이어진다", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("용량 참");
      });
    const log = makeActivityLogger(vi.fn().mockResolvedValue({}),
                                   { storageKey: KEY });
    expect(() => log.record("session_started")).not.toThrow();
    spy.mockRestore();
  });
});

describe("창이 닫힐 때", () => {
  test("sendBeacon으로 넘긴다", () => {
    // 이때는 보통의 요청이 취소된다 — 브라우저가 페이지를 버리면서 진행 중인
    // fetch도 같이 버린다.
    const beacon = vi.fn().mockReturnValue(true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: beacon });

    const log = makeActivityLogger(vi.fn().mockResolvedValue({}));
    log.record("session_ended");
    const ok = log.flushOnExit("/activity", (events) => ({ events }));

    expect(ok).toBe(true);
    expect(beacon).toHaveBeenCalledWith("/activity", expect.any(Blob));
    vi.unstubAllGlobals();
  });

  test("보낸 뒤에도 큐에서 지우지 않는다", () => {
    // 응답을 못 받으므로 저장됐는지 알 수 없다. 다음 접속의 재전송이
    // event_id로 걸러진다.
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: () => true });
    const log = makeActivityLogger(vi.fn().mockResolvedValue({}));
    log.record("session_ended");
    log.flushOnExit("/activity", (events) => ({ events }));
    expect(log.pending).toBe(1);
    vi.unstubAllGlobals();
  });

  test("보낼 것이 없으면 아무것도 안 한다", () => {
    const beacon = vi.fn();
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: beacon });
    makeActivityLogger(vi.fn()).flushOnExit("/a", (e) => e);
    expect(beacon).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  test("sendBeacon이 없거나 실패해도 던지지 않는다", () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      sendBeacon: () => {
        throw new Error("못 씀");
      },
    });
    const log = makeActivityLogger(vi.fn());
    log.record("session_ended");
    expect(log.flushOnExit("/a", (e) => e)).toBe(false);
    vi.unstubAllGlobals();
  });
});
