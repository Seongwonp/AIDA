/**
 * R6 — 실제 화면의 흐름 전체 (docs/25).
 *
 * 열기 → 연속 판정 → 저장 실패 → 재시도 → 새로고침 → CSV.
 *
 * R1~R5는 각각의 위험을 따로 재현했다. 여기서는 **한 흐름으로 잇는다** —
 * 조각이 다 맞아도 이어 붙이면 어긋나는 자리가 있기 때문이다.
 *
 * **이것은 jsdom이지 브라우저가 아니다.** 실제 렌더링·레이아웃·브라우저 저장
 * 정책은 여기서 못 본다(docs/testing-boundary.md).
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
import { keyOf, loadVerdicts, toCsv } from "./reviewQueueLogic";

const DS = "ds-flow";

function item(over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    rank: 1, image: "a.png", label_index: 0, suspicion: "width",
    label: "가로 길이 어긋남", severity: 0.5, detail: "예측보다 28% 작음",
    box: [10, 20, 110, 220], ...over,
  };
}
const ITEMS = [
  item({ rank: 1, label_index: 0 }),
  item({ rank: 2, label_index: 1 }),
  item({ rank: 3, label_index: 2 }),
];

async function judge(n: number) {
  const buttons = screen.getAllByRole("button", { name: "오류" });
  await act(async () => { buttons[n].click(); });
}

beforeEach(() => {
  localStorage.clear();
  getVerdicts.mockReset().mockResolvedValue({ verdicts: {}, updated_at: null });
  putVerdicts.mockReset().mockResolvedValue({ verdicts: {} });
});
afterEach(cleanup);

describe("R6 흐름 전체", () => {
  test("열기 → 연속 판정 → 저장 실패 → 재시도 → 새로고침 → CSV", async () => {
    // 서버를 흉내 낸다. 실패하는 동안에는 아무것도 안 받는다.
    let serverState: Record<string, string> = {};
    let failing = false;
    putVerdicts.mockImplementation((_id: string, v: Record<string, string>) => {
      if (failing) return Promise.reject(new Error("끊김"));
      serverState = { ...v };
      return Promise.resolve({ verdicts: serverState });
    });

    const first = render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => expect(getVerdicts).toHaveBeenCalled());

    // 연속 판정 — 잘 들어간다.
    await judge(0);
    await judge(1);
    await waitFor(() => expect(serverState[keyOf(ITEMS[1])]).toBe("hit"));

    // 네트워크가 끊긴다.
    failing = true;
    await judge(2);

    // **실패를 화면이 말해야 한다.**
    await waitFor(() => {
      expect(screen.getByText(/서버에 저장하지 못했습니다/)).toBeTruthy();
    });
    // 브라우저에는 남아 있어 검수는 이어진다.
    expect(loadVerdicts(DS)[keyOf(ITEMS[2])]).toBe("hit");
    // 서버는 아직 옛 상태다.
    expect(serverState[keyOf(ITEMS[2])]).toBeUndefined();

    // 네트워크가 돌아오고 **사용자가 다시 시도한다.**
    failing = false;
    const retry = screen.getByRole("button", { name: /다시 시도/ });
    await act(async () => { retry.click(); });

    await waitFor(() => {
      expect(serverState[keyOf(ITEMS[2])]).toBe("hit");
    });
    // 성공했으면 경고가 사라져야 한다.
    await waitFor(() => {
      expect(screen.queryByText(/서버에 저장하지 못했습니다/)).toBeNull();
    });

    // 새로고침 — 서버가 합친 상태를 돌려준다.
    first.unmount();
    getVerdicts.mockResolvedValue({
      verdicts: serverState, updated_at: "2026-09-09T00:00:00+00:00",
    });
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => {
      const pressed = screen.getAllByRole("button", { name: "오류" })
        .filter((b) => b.getAttribute("aria-pressed") === "true");
      expect(pressed).toHaveLength(3);
    });

    // CSV가 화면과 같아야 한다.
    const rows = toCsv(ITEMS, loadVerdicts(DS)).split("\n");
    expect(rows).toHaveLength(4);
    for (let i = 1; i <= 3; i++) expect(rows[i]).toContain("오류 맞음");
  });

  test("재시도가 또 실패하면 계속 말한다", async () => {
    putVerdicts.mockRejectedValue(new Error("끊김"));
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => expect(getVerdicts).toHaveBeenCalled());
    await judge(0);

    await waitFor(() => {
      expect(screen.getByText(/서버에 저장하지 못했습니다/)).toBeTruthy();
    });
    const retry = screen.getByRole("button", { name: /다시 시도/ });
    await act(async () => { retry.click(); });
    // 여전히 실패 — 조용해지면 안 된다.
    await waitFor(() => {
      expect(screen.getByText(/서버에 저장하지 못했습니다/)).toBeTruthy();
    });
  });

  test("실패한 적이 없으면 재시도 단추가 없다", async () => {
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => expect(getVerdicts).toHaveBeenCalled());
    await judge(0);
    expect(screen.queryByRole("button", { name: /다시 시도/ })).toBeNull();
  });
});
