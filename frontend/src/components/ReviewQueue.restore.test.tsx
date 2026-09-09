/**
 * R3 — 복원의 의미를 구분한다 (docs/25).
 *
 * 화면은 "서버가 비었으면 브라우저 것을 쓴다"였다. 그런데 **서버가 비는 이유가
 * 셋**이고 뜻이 서로 다르다.
 *
 *   1. 아직 아무것도 저장 안 됨   → 브라우저 것이 유일한 원본이다. 살려야 한다.
 *   2. 판정을 전부 지웠다          → 지운 것이 최신이다. **되살리면 안 된다.**
 *   3. 서버에 못 닿았다            → 판단할 근거가 없다. 브라우저 것으로 이어간다.
 *
 * 서버 응답의 `updated_at`이 1과 2를 갈라준다 — 한 번이라도 저장했으면 값이
 * 있다. 화면이 그걸 안 보고 있었다.
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
import { keyOf, loadVerdicts, STORE } from "./reviewQueueLogic";

const DS = "ds-restore";

function item(over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    rank: 1, image: "a.png", label_index: 0, suspicion: "width",
    label: "가로 길이 어긋남", severity: 0.5, detail: "",
    box: [10, 20, 110, 220], ...over,
  };
}
const ITEMS = [item({ rank: 1, label_index: 0 }), item({ rank: 2, label_index: 1 })];

/** 브라우저에 이미 판정이 있는 상태를 만든다. */
function seedLocal() {
  localStorage.setItem(STORE(DS), JSON.stringify({ [keyOf(ITEMS[0])]: "hit" }));
}

async function openQueue() {
  render(<ReviewQueue items={ITEMS} datasetId={DS} />);
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

beforeEach(() => {
  localStorage.clear();
  getVerdicts.mockReset();
  putVerdicts.mockReset().mockResolvedValue({ verdicts: {} });
});
afterEach(cleanup);

describe("R3 복원의 의미", () => {
  test("아직 아무것도 저장 안 됐으면 브라우저 것을 살린다", async () => {
    seedLocal();
    // 파일이 없으면 서버는 updated_at 없이 빈 것을 준다.
    getVerdicts.mockResolvedValue({ verdicts: {}, updated_at: null });
    await openQueue();
    await waitFor(() => {
      expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit");
    });
  });

  test("판정을 전부 지웠으면 브라우저 사본으로 되살리지 않는다", async () => {
    seedLocal();
    // 한 번이라도 저장했으면 updated_at이 있다. 빈 것은 '지웠다'는 뜻이다.
    getVerdicts.mockResolvedValue({
      verdicts: {}, updated_at: "2026-09-09T00:00:00+00:00",
    });
    await openQueue();
    await waitFor(() => {
      expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBeUndefined();
    });
    // 화면에도 눌린 판정이 없어야 한다.
    const pressed = screen.getAllByRole("button", { name: "오류" })
      .filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(0);
  });

  test("지운 서버 응답이 와도 기다리는 동안 내린 판정은 남는다", async () => {
    // R1과 R3가 만나는 자리다. 서버는 '전부 지웠다'고 하는데 사용자는 그
    // 사이에 새로 판정했다 — 사용자가 방금 한 일이 더 최신이다.
    seedLocal();
    let release!: (v: unknown) => void;
    getVerdicts.mockReturnValue(new Promise((r) => { release = r; }));
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);

    const buttons = screen.getAllByRole("button", { name: "오류" });
    await act(async () => { buttons[1].click(); });      // 새 판정

    await act(async () => {
      release({ verdicts: {}, updated_at: "2026-09-09T00:00:00+00:00" });
      await Promise.resolve();
    });

    await waitFor(() => {
      // 지운 옛 판정은 사라지고
      expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBeUndefined();
      // 방금 내린 것은 남는다
      expect(loadVerdicts(DS)[keyOf(ITEMS[1])]).toBe("hit");
    });
  });

  test("서버 파일이 깨졌으면 브라우저 사본을 버리지 않는다", async () => {
    // 손상은 '지웠다'가 아니다. 서버가 무엇을 갖고 있었는지 모르는 상태라
    // 응답 실패와 같이 다뤄야 한다 (docs/25 R4).
    seedLocal();
    getVerdicts.mockResolvedValue({ verdicts: {}, updated_at: null, damaged: true });
    await openQueue();
    expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit");
  });

  test("서버 파일이 깨졌으면 화면에 말한다", async () => {
    seedLocal();
    getVerdicts.mockResolvedValue({ verdicts: {}, updated_at: null, damaged: true });
    await openQueue();
    await waitFor(() => {
      expect(screen.getByText(/저장 파일이 손상/)).toBeTruthy();
    });
  });

  test("깨진 채로 저장된 것처럼 보여도 사본을 안 지운다", async () => {
    // updated_at이 있는데 damaged이면 '지웠다'로 읽으면 안 된다.
    seedLocal();
    getVerdicts.mockResolvedValue({
      verdicts: {}, updated_at: "2026-09-09T00:00:00+00:00", damaged: true,
    });
    await openQueue();
    expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit");
  });

  test("서버에 못 닿으면 브라우저 것으로 이어간다", async () => {
    seedLocal();
    getVerdicts.mockRejectedValue(new Error("오프라인"));
    await openQueue();
    expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit");
  });

  test("서버에 판정이 있으면 그것이 이긴다", async () => {
    seedLocal();
    getVerdicts.mockResolvedValue({
      verdicts: { [keyOf(ITEMS[1])]: "miss" },
      updated_at: "2026-09-09T00:00:00+00:00",
    });
    await openQueue();
    await waitFor(() => {
      expect(loadVerdicts(DS)[keyOf(ITEMS[1])]).toBe("miss");
      expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBeUndefined();
    });
  });
});
