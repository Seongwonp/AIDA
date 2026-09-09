/**
 * 작업 기록의 규칙 (docs/pilot-evaluation-plan.md).
 *
 * 여기서 고정하는 것은 **화면이 무엇을 남기는가**다. 시간 계산은 화면이 하지
 * 않는다 — `experiment/evaluation/activity.py`가 나중에 한다.
 */
import { describe, expect, test, vi } from "vitest";

import { makeActivityLogger, newSessionId, now } from "./activityLog";

describe("시각", () => {
  test("벽시계와 단조 시계를 둘 다 남긴다", () => {
    // 벽시계는 자정을 넘거나 시스템 시계가 바뀌면 뒤로 갈 수 있어 길이를 못
    // 잰다. 단조 시계는 새로 뜨면 0부터라 언제인지를 못 말한다.
    const got = now();
    expect(got.at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(typeof got.elapsed_ms).toBe("number");
    expect(got.elapsed_ms).toBeGreaterThanOrEqual(0);
  });

  test("단조 시계는 음수가 되지 않는다", () => {
    const spy = vi.spyOn(performance, "now").mockReturnValue(-5);
    expect(now().elapsed_ms).toBe(0);
    spy.mockRestore();
  });

  test("세션 이름은 매번 다르다", () => {
    expect(newSessionId()).not.toBe(newSessionId());
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

  test("남긴 것에 세션·시각·후보가 들어간다", async () => {
    const send = vi.fn().mockResolvedValue({});
    const log = makeActivityLogger(send);
    log.record("verdict_set", "L123", { verdict: "hit" });
    await log.flush();

    const [batch] = send.mock.calls[0];
    expect(batch[0]).toMatchObject({
      event: "verdict_set",
      canonical_candidate_id: "L123",
      session_id: log.sessionId,
      meta: { verdict: "hit" },
    });
    expect(batch[0].at).toBeTruthy();
  });
});

describe("실패해도 판정을 막지 않는다", () => {
  test("실패하면 큐에 되돌려 다음에 같이 보낸다", async () => {
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
    expect(batch.map((e: { event: string }) => e.event))
      .toEqual(["session_started", "moved_next"]);
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
});

describe("세션", () => {
  test("새 세션을 시작하면 이름이 바뀐다", () => {
    const log = makeActivityLogger(vi.fn().mockResolvedValue({}));
    const before = log.sessionId;
    log.startSession();
    expect(log.sessionId).not.toBe(before);
  });
});
