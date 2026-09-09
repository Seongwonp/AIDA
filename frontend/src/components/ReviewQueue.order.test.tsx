/**
 * R2 — 저장 요청의 순서가 뒤집히면 (docs/25).
 *
 * `setVerdict`은 판정할 때마다 `putVerdicts(datasetId, next)`를 부르고 **기다리지
 * 않는다.** 판정 전체를 덮어쓰는 API이므로, 두 요청이 순서 바뀌어 도착하면
 * **먼저 보낸 옛 상태가 나중에 도착해 최신을 지운다.**
 *
 * 서버가 실제로 그렇게 뒤집힐지는 네트워크에 달렸다. 여기서는 그 상황을
 * 만들어 **클라이언트가 그것을 견디는지**를 본다.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";

import type { ReviewQueueItem } from "../types";

const getVerdicts = vi.fn();
const putVerdicts = vi.fn();
vi.mock("../api", () => ({
  getVerdicts: (...a: unknown[]) => getVerdicts(...a),
  putVerdicts: (...a: unknown[]) => putVerdicts(...a),
}));
vi.mock("./BoxPreview", () => ({ BoxPreview: () => null }));

import { ReviewQueue } from "./ReviewQueue";
import { keyOf } from "./reviewQueueLogic";

const DS = "ds-order";

function item(over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    rank: 1, image: "a.png", label_index: 0, suspicion: "width",
    label: "가로 길이 어긋남", severity: 0.5, detail: "",
    box: [10, 20, 110, 220], ...over,
  };
}
const ITEMS = [item({ rank: 1, label_index: 0 }), item({ rank: 2, label_index: 1 })];

/** 서버를 흉내 낸다 — 요청이 **도착한 순서대로** 파일을 덮어쓴다. */
function makeServer() {
  const server: { state: Record<string, string> } = { state: {} };
  const pending: Array<() => void> = [];
  putVerdicts.mockImplementation((_id: string, v: Record<string, string>) => {
    const snapshot = { ...v };
    return new Promise<void>((resolve) => {
      pending.push(() => { server.state = snapshot; resolve(); });
    });
  });
  return {
    server,
    /**
     * 대기 중인 요청을 **거꾸로** 도착시킨다. 남는 것이 없을 때까지 반복한다.
     *
     * 기제가 아니라 **성질**을 잰다 — 어떤 순서로 도착하든 마지막에 서버에
     * 남은 것이 클라이언트의 최신 상태여야 한다. 요청을 한 줄로 세우면
     * 애초에 뒤집힐 것이 없고, 그것도 이 검사를 통과하는 방법이다.
     */
    drainReversed: async () => {
      for (let round = 0; round < 10; round++) {
        const batch = pending.splice(0).reverse();
        if (batch.length === 0) break;
        // no-await-in-loop 경고가 뜨지만 도착 순서를 라운드별로
        // 통제하는 것이 이 검사의 목적이다.
        await act(async () => {
          for (const fire of batch) fire();
          await Promise.resolve();
          await Promise.resolve();
        });
      }
    },
    count: () => pending.length,
  };
}

async function judge(n: number) {
  const buttons = screen.getAllByRole("button", { name: "오류" });
  await act(async () => { buttons[n].click(); });
}

beforeEach(() => {
  localStorage.clear();
  getVerdicts.mockReset().mockResolvedValue({ verdicts: {} });
  putVerdicts.mockReset();
});
afterEach(cleanup);

describe("R2 저장 순서 역전", () => {
  test("먼저 보낸 요청이 늦게 도착해도 최신 판정이 남는다", async () => {
    const net = makeServer();
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => expect(getVerdicts).toHaveBeenCalled());

    await judge(0);            // {0: hit}
    await judge(1);            // {0: hit, 1: hit}

    // 도착 순서를 거꾸로 뒤집는다.
    await net.drainReversed();

    await waitFor(() => {
      expect(net.server.state[keyOf(ITEMS[1])]).toBe("hit");
    });
    expect(net.server.state[keyOf(ITEMS[0])]).toBe("hit");
  });

  test("지운 판정이 옛 요청으로 되살아나지 않는다", async () => {
    const net = makeServer();
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => expect(getVerdicts).toHaveBeenCalled());

    await judge(0);            // {0: hit}
    await judge(0);            // 다시 눌러 지움 → {}

    await net.drainReversed();   // 거꾸로 도착

    await waitFor(() => {
      expect(net.server.state[keyOf(ITEMS[0])]).toBeUndefined();
    });
  });
});
