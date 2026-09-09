/**
 * R1 — 초기 서버 조회가 신규 판정을 덮어쓰는가 (docs/25).
 *
 * 정적 검토에서 나온 **위험 후보**다. 화면이 열릴 때 `getVerdicts`를 부르고,
 * 응답이 오면 `setVerdicts(next)`로 **통째로 갈아끼운다.** 응답이 늦게 오는
 * 동안 사용자가 판정하면 그 판정이 사라질 수 있다.
 *
 * **순수 함수로는 재현할 수 없다.** 결함이 있다면 컴포넌트의 상태 갱신 순서에
 * 있으므로 실제 React 화면에서 재현해야 한다.
 *
 * **재현되지 않으면 결함을 만들어내지 않는다** — 조건과 결과만 남긴다.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";

import type { ReviewQueueItem } from "../types";

// api를 가로채 응답 시점을 우리가 쥔다.
const getVerdicts = vi.fn();
const putVerdicts = vi.fn();
vi.mock("../api", () => ({
  getVerdicts: (...a: unknown[]) => getVerdicts(...a),
  putVerdicts: (...a: unknown[]) => putVerdicts(...a),
}));
// 이미지 미리보기는 이 검사와 무관하고 fetch를 부른다.
vi.mock("./BoxPreview", () => ({ BoxPreview: () => null }));

import { ReviewQueue } from "./ReviewQueue";
import { keyOf, loadVerdicts, toCsv } from "./reviewQueueLogic";

const DS = "ds-race";

function item(over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    rank: 1, image: "a.png", label_index: 0, suspicion: "width",
    label: "가로 길이 어긋남", severity: 0.5, detail: "예측보다 28% 작습니다",
    box: [10, 20, 110, 220], ...over,
  };
}
const ITEMS = [item({ rank: 1, label_index: 0 }), item({ rank: 2, label_index: 1 })];

/** "오류" 버튼을 눌러 판정한다. 화면이 실제로 하는 일과 같다. */
async function judgeFirst() {
  const buttons = screen.getAllByRole("button", { name: "오류" });
  await act(async () => { buttons[0].click(); });
}

beforeEach(() => {
  localStorage.clear();
  getVerdicts.mockReset();
  putVerdicts.mockReset().mockResolvedValue({ verdicts: {} });
});
afterEach(cleanup);

describe("R1 초기 조회 경쟁", () => {
  test("응답이 늦게 오는 동안 내린 판정이 살아남는다", async () => {
    // 서버에는 예전 판정이 있고, 응답은 우리가 풀어줄 때까지 안 온다.
    let release!: (v: unknown) => void;
    getVerdicts.mockReturnValue(new Promise((r) => { release = r; }));

    render(<ReviewQueue items={ITEMS} datasetId={DS} />);

    // 응답 전에 사용자가 판정한다.
    await judgeFirst();
    expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit");

    // 이제 **오래된** 서버 응답이 도착한다. 두 번째 후보만 들어 있다.
    await act(async () => {
      release({ verdicts: { [keyOf(ITEMS[1])]: "miss" } });
      await Promise.resolve();
    });

    await waitFor(() => {
      // 방금 내린 판정이 남아 있어야 한다.
      expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit");
    });
    // 서버에 있던 것도 잃지 않아야 한다.
    expect(loadVerdicts(DS)[keyOf(ITEMS[1])]).toBe("miss");
  });

  test("기다리는 동안 지운 판정이 서버 것으로 되살아나지 않는다", async () => {
    // 같은 값을 다시 누르면 판정이 지워진다. 그 '지움'도 서버보다 최신이다.
    let release!: (v: unknown) => void;
    getVerdicts.mockReturnValue(new Promise((r) => { release = r; }));
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);

    await judgeFirst();                       // hit
    await judgeFirst();                       // 다시 눌러 지움
    expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBeUndefined();

    await act(async () => {
      release({ verdicts: { [keyOf(ITEMS[0])]: "hit" } });   // 서버엔 아직 남아 있다
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBeUndefined();
    });
  });

  test("기다리는 동안 내린 판정은 서버에도 올라간다", async () => {
    let release!: (v: unknown) => void;
    getVerdicts.mockReturnValue(new Promise((r) => { release = r; }));
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await judgeFirst();
    putVerdicts.mockClear();
    await act(async () => {
      release({ verdicts: { [keyOf(ITEMS[1])]: "miss" } });
      await Promise.resolve();
    });
    await waitFor(() => {
      const sent = putVerdicts.mock.calls.at(-1)?.[1] as Record<string, string>;
      expect(sent?.[keyOf(ITEMS[0])]).toBe("hit");
      expect(sent?.[keyOf(ITEMS[1])]).toBe("miss");
    });
  });

  test("판정 전에 응답이 오면 서버 것을 쓴다", async () => {
    getVerdicts.mockResolvedValue({ verdicts: { [keyOf(ITEMS[1])]: "miss" } });
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => {
      expect(loadVerdicts(DS)[keyOf(ITEMS[1])]).toBe("miss");
    });
  });

  test("조회가 실패해도 검수는 이어진다", async () => {
    getVerdicts.mockRejectedValue(new Error("서버 없음"));
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await judgeFirst();
    expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit");
  });

  test("새로고침하면 살아남은 판정이 화면에 다시 뜬다", async () => {
    // 저장만 되고 화면 복원이 안 되면 검수자는 잃었다고 본다.
    let release!: (v: unknown) => void;
    getVerdicts.mockReturnValue(new Promise((r) => { release = r; }));
    const first = render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await judgeFirst();
    await act(async () => {
      release({ verdicts: { [keyOf(ITEMS[1])]: "miss" } });
      await Promise.resolve();
    });
    await waitFor(() => expect(loadVerdicts(DS)[keyOf(ITEMS[0])]).toBe("hit"));
    first.unmount();

    // 새로고침 — 이번엔 서버가 합친 것을 돌려준다.
    getVerdicts.mockResolvedValue({ verdicts: loadVerdicts(DS) });
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await waitFor(() => {
      const pressed = screen.getAllByRole("button", { name: "오류" })
        .filter((b) => b.getAttribute("aria-pressed") === "true");
      expect(pressed).toHaveLength(1);
    });
  });

  test("살아남은 판정이 CSV에도 그대로 나온다", async () => {
    let release!: (v: unknown) => void;
    getVerdicts.mockReturnValue(new Promise((r) => { release = r; }));
    render(<ReviewQueue items={ITEMS} datasetId={DS} />);
    await judgeFirst();
    await act(async () => {
      release({ verdicts: { [keyOf(ITEMS[1])]: "miss" } });
      await Promise.resolve();
    });
    await waitFor(() => {
      const csv = toCsv(ITEMS, loadVerdicts(DS));
      expect(csv.split("\n")[1]).toContain("오류 맞음");
    });
  });
});
