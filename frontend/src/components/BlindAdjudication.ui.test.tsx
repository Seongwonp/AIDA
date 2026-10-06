/**
 * 가림 판정 화면의 조작 — 단축키·선택 표시·첫 방문 튜토리얼·진행 막대.
 *
 * 단축키는 **클릭과 같은 길**을 타야 한다(`verdict_set`·저장 기록이 같아야 한다). 그래서 저장 호출과
 * 작업 기록을 클릭 때와 견준다.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";

const getBlindQueue = vi.fn();
const putAdjudications = vi.fn();
const postActivity = vi.fn();
vi.mock("../api", () => ({
  getBlindQueue: (...a: unknown[]) => getBlindQueue(...a),
  putAdjudications: (...a: unknown[]) => putAdjudications(...a),
  postActivity: (...a: unknown[]) => postActivity(...a),
  getLabelBoxes: () => Promise.resolve({ image: "a.jpg", labels: [] }),
  API_BASE_URL: "",
}));
vi.mock("./AdjudicationView", () => ({ AdjudicationView: () => null }));

import { BlindAdjudication } from "./BlindAdjudication";
import { TUTORIAL_KEY } from "./blindTutorialStorage";

const DS = "0123456789ab";
const EVAL = "e1";

function cand(over: Record<string, unknown> = {}) {
  return {
    canonical_candidate_id: "A",
    image: "a.jpg",
    label_index: 0,
    box: [1, 2, 3, 4],
    verdict: null,
    unique_error_id: null,
    ...over,
  };
}

function queue(candidates: unknown[]) {
  return {
    evaluation_id: EVAL,
    dataset_id: DS,
    candidate_set_hash: "h1",
    candidates,
    damaged: false,
  };
}

function show() {
  return render(<BlindAdjudication datasetId={DS} evaluationId={EVAL} />);
}

async function press(key: string, target: Element | Document = document.body) {
  await act(async () => {
    fireEvent.keyDown(target, { key });
  });
}

function logged() {
  return postActivity.mock.calls.flatMap((call) => call[3] as Array<{
    event: string; canonical_candidate_id: string | null; meta: Record<string, unknown>;
  }>);
}

async function nextStep() {
  await act(async () => screen.getByRole("button", { name: "다음 단계" }).click());
}

const pressed = () =>
  screen.getAllByRole("button")
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.textContent);

beforeEach(() => {
  getBlindQueue.mockReset();
  putAdjudications.mockReset();
  putAdjudications.mockResolvedValue({});
  postActivity.mockReset();
  postActivity.mockResolvedValue({});
  localStorage.clear();
  // 단축키 검사는 튜토리얼을 이미 본 상태에서 한다. 튜토리얼 검사는 따로 지운다.
  localStorage.setItem(TUTORIAL_KEY, "done");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("단축키", () => {
  test("1·2·3이 오류였다·오류 아니었다·모르겠다를 고르고 클릭과 같이 저장한다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");

    await press("1");
    await waitFor(() => expect(putAdjudications).toHaveBeenCalledTimes(1));
    expect(putAdjudications.mock.calls[0][3][0]).toMatchObject({ verdict: "hit" });
    expect(pressed()).toEqual(["오류였다"]);

    await press("2");
    await waitFor(() => expect(putAdjudications).toHaveBeenCalledTimes(2));
    expect(putAdjudications.mock.calls[1][3][0]).toMatchObject({ verdict: "miss" });
    expect(pressed()).toEqual(["오류 아니었다"]);

    await press("3");
    await waitFor(() => expect(putAdjudications).toHaveBeenCalledTimes(3));
    expect(putAdjudications.mock.calls[2][3][0]).toMatchObject({ verdict: "hold" });
    expect(pressed()).toEqual(["모르겠다"]);
  });

  test("단축키 판정의 기록이 클릭 판정의 기록과 같다", async () => {
    async function run(how: "key" | "click") {
      postActivity.mockClear();
      getBlindQueue.mockResolvedValue(queue([cand()]));
      const { unmount } = show();
      await screen.findByText("a.jpg");
      if (how === "key") await press("1");
      else await act(async () => screen.getByRole("button", { name: "오류였다" }).click());
      await screen.findByText("저장됨");
      await act(async () => unmount());
      return logged()
        .filter((e) => e.event.startsWith("verdict") || e.event.startsWith("save"))
        .map((e) => [e.event, e.canonical_candidate_id, e.meta]);
    }
    const byKey = await run("key");
    const byClick = await run("click");
    expect(byKey).toEqual(byClick);
    expect(byKey.map((e) => e[0])).toEqual(["verdict_set", "save_started", "save_succeeded"]);
  });

  test("←/→가 이전/다음으로 옮기고 이동을 기록한다", async () => {
    getBlindQueue.mockResolvedValue(queue([
      cand({ canonical_candidate_id: "A", image: "a.jpg" }),
      cand({ canonical_candidate_id: "B", image: "b.jpg" }),
    ]));
    const { unmount } = show();
    await screen.findByText("a.jpg");

    await press("ArrowRight");
    await screen.findByText("b.jpg");
    await press("ArrowRight");          // 마지막이라 더 안 간다
    await screen.findByText("b.jpg");
    await press("ArrowLeft");
    await screen.findByText("a.jpg");
    await act(async () => unmount());

    const moves = logged().map((e) => e.event)
      .filter((e) => e.startsWith("moved_"));
    expect(moves).toEqual(["moved_next", "moved_previous"]);
    expect(putAdjudications).not.toHaveBeenCalled();
  });

  test("입력칸에서 글자를 칠 때는 동작하지 않는다", async () => {
    getBlindQueue.mockResolvedValue(queue([
      cand({ canonical_candidate_id: "A", image: "a.jpg" }),
      cand({ canonical_candidate_id: "B", image: "b.jpg" }),
    ]));
    show();
    await screen.findByText("a.jpg");

    const input = document.createElement("input");
    const area = document.createElement("textarea");
    document.body.append(input, area);
    await act(async () => {
      for (const el of [input, area]) {
        for (const key of ["1", "2", "3", "ArrowRight"]) fireEvent.keyDown(el, { key });
      }
    });
    input.remove();
    area.remove();

    expect(putAdjudications).not.toHaveBeenCalled();
    expect(pressed()).toEqual([]);
    expect(screen.getByText("a.jpg")).toBeTruthy();
  });

  test("수정 키를 같이 누르거나 길게 눌러 반복되면 동작하지 않는다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");

    await act(async () => {
      fireEvent.keyDown(document.body, { key: "1", ctrlKey: true });
      fireEvent.keyDown(document.body, { key: "1", repeat: true });
    });
    expect(putAdjudications).not.toHaveBeenCalled();
  });

  test("튜토리얼이 떠 있으면 동작하지 않는다", async () => {
    localStorage.removeItem(TUTORIAL_KEY);
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");
    expect(screen.getByRole("dialog")).toBeTruthy();

    await press("1");
    expect(putAdjudications).not.toHaveBeenCalled();
  });

  test("버튼에 단축키가 적혀 있다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");
    expect(screen.getByRole("button", { name: "오류였다" }).getAttribute("aria-keyshortcuts")).toBe("1");
    expect(screen.getByRole("button", { name: "오류 아니었다" }).getAttribute("aria-keyshortcuts")).toBe("2");
    expect(screen.getByRole("button", { name: "모르겠다" }).getAttribute("aria-keyshortcuts")).toBe("3");
    expect(screen.getByRole("button", { name: "이전" }).getAttribute("aria-keyshortcuts")).toBe("ArrowLeft");
    expect(screen.getByRole("button", { name: "다음" }).getAttribute("aria-keyshortcuts")).toBe("ArrowRight");
  });
});

describe("선택 표시", () => {
  test("고른 판정만 aria-pressed가 참이고, 판정 취소하면 모두 거짓이다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand(), cand({ canonical_candidate_id: "B" })]));
    show();
    await screen.findByText("a.jpg");
    for (const name of ["오류였다", "오류 아니었다", "모르겠다"]) {
      expect(screen.getByRole("button", { name }).getAttribute("aria-pressed")).toBe("false");
    }

    await act(async () => screen.getByRole("button", { name: "오류 아니었다" }).click());
    expect(screen.getByRole("button", { name: "오류 아니었다" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "오류였다" }).getAttribute("aria-pressed")).toBe("false");

    await act(async () => screen.getByRole("button", { name: "판정 취소" }).click());
    expect(pressed()).toEqual([]);
  });
});

describe("첫 방문 튜토리얼", () => {
  test("처음 오면 뜨고, 끝까지 넘겨 닫으면 기억한다", async () => {
    localStorage.removeItem(TUTORIAL_KEY);
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toMatch(/상자 색/);

    await nextStep();
    await nextStep();
    await nextStep();
    expect(screen.getByRole("dialog").textContent).toMatch(/키보드/);
    await act(async () => screen.getByRole("button", { name: "판정 시작" }).click());

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(localStorage.getItem(TUTORIAL_KEY)).toBe("done");
  });

  test("이미 봤으면 안 뜨고, 다시 보기로 열 수 있다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");
    expect(screen.queryByRole("dialog")).toBeNull();

    await act(async () => screen.getByRole("button", { name: "튜토리얼 다시 보기" }).click());
    expect(screen.getByRole("dialog")).toBeTruthy();
    await act(async () => screen.getByRole("button", { name: "건너뛰기" }).click());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("Esc로 닫는다", async () => {
    localStorage.removeItem(TUTORIAL_KEY);
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByRole("dialog");
    await press("Escape");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("저장소가 막혀도 화면이 뜨고 튜토리얼을 닫을 수 있다", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");
    expect(screen.getByRole("dialog")).toBeTruthy();

    await act(async () => screen.getByRole("button", { name: "건너뛰기" }).click());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "오류였다" })).toBeTruthy();
  });

  test("튜토리얼에 후보·방법 이름·점수 값이 없다", async () => {
    localStorage.removeItem(TUTORIAL_KEY);
    getBlindQueue.mockResolvedValue(queue([cand({ image: "scene_0042.jpg" })]));
    show();
    await screen.findByRole("dialog");
    const texts = [screen.getByRole("dialog").innerHTML];
    await nextStep();
    texts.push(screen.getByRole("dialog").innerHTML);
    await nextStep();
    texts.push(screen.getByRole("dialog").innerHTML);
    await nextStep();
    texts.push(screen.getByRole("dialog").innerHTML);
    const all = texts.join("\n");
    expect(all).toMatch(/키보드/);   // 네 단계를 다 봤다
    expect(all).not.toMatch(/scene_0042|<img|<canvas|aida_v|iou_baseline|objectlab|random|무작위|\d\.\d{2}/i);
  });
});

describe("진행 막대", () => {
  test("판정 수·전체·남은 수를 막대와 글로 보여 준다", async () => {
    getBlindQueue.mockResolvedValue(queue([
      cand({ canonical_candidate_id: "A", verdict: "hit" }),
      cand({ canonical_candidate_id: "B", image: "b.jpg" }),
      cand({ canonical_candidate_id: "C", image: "c.jpg" }),
      cand({ canonical_candidate_id: "D", image: "d.jpg" }),
    ]));
    show();
    await screen.findByText("b.jpg");

    const bar = screen.getByRole("progressbar", { name: "판정 진행" }) as HTMLProgressElement;
    expect(bar.value).toBe(1);
    expect(bar.max).toBe(4);
    screen.getByText("1 / 4 판정 (남은 3)");

    await act(async () => screen.getByRole("button", { name: "모르겠다" }).click());
    expect(bar.value).toBe(2);
    screen.getByText("2 / 4 판정 (남은 2)");
  });

  test("저장 상태를 저장 중·저장됨·저장 실패로 가른다", async () => {
    let release!: (v: unknown) => void;
    putAdjudications.mockReturnValueOnce(new Promise((r) => (release = r)));
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");

    await act(async () => screen.getByRole("button", { name: "오류였다" }).click());
    expect(screen.getByText("저장 중…").className).toMatch(/save-saving/);
    await act(async () => release({}));
    expect((await screen.findByText("저장됨")).className).toMatch(/save-saved/);

    await act(async () => screen.getByRole("button", { name: "모르겠다" }).click());
    expect((await screen.findByText(/^저장 실패/)).className).toMatch(/save-failed/);
  });
});

describe("가림", () => {
  test("묶음에 점수·순위·출처가 섞여 와도 화면에 안 뜬다", async () => {
    // 서버가 실수로 더 보내도 화면은 정해 둔 칸만 그린다.
    getBlindQueue.mockResolvedValue(queue([cand({
      score: 0.8731, rank: 17, method: "aida_v2_candidate_iou",
      source: "random_sample", candidate_source: "auxiliary_sample",
    })]));
    show();
    await screen.findByText("a.jpg");
    const html = document.body.innerHTML;
    expect(html).not.toMatch(/0\.8731|aida_v2|random_sample|auxiliary_sample|\b17\b/);
    expect(document.body.textContent ?? "").not.toMatch(/\d+위|점수:|순위:|출처:/);
  });
});
