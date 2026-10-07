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
  /** 새로 띄운 화면에서 키 하나를 눌러 저장된 판정값을 돌려준다. */
  async function savedByKey(key: string) {
    putAdjudications.mockClear();
    getBlindQueue.mockResolvedValue(queue([cand(), cand({ canonical_candidate_id: "B", image: "b.jpg" })]));
    const { unmount } = show();
    await screen.findByText("a.jpg");
    await press(key);
    await waitFor(() => expect(putAdjudications).toHaveBeenCalledTimes(1));
    const row = putAdjudications.mock.calls[0][3][0];
    await act(async () => unmount());
    return [row.canonical_candidate_id, row.verdict];
  }

  test("1·2·3이 오류 있음·오류 없음·판단 보류를 고르고 hit·miss·hold로 저장한다", async () => {
    expect(await savedByKey("1")).toEqual(["A", "hit"]);
    expect(await savedByKey("2")).toEqual(["A", "miss"]);
    expect(await savedByKey("3")).toEqual(["A", "hold"]);
  });

  test("단축키 판정의 기록이 클릭 판정의 기록과 같다", async () => {
    async function run(how: "key" | "click") {
      postActivity.mockClear();
      getBlindQueue.mockResolvedValue(queue([cand()]));
      const { unmount } = show();
      await screen.findByText("a.jpg");
      if (how === "key") await press("1");
      else await act(async () => screen.getByRole("button", { name: "오류 있음" }).click());
      await screen.findByText(/모두 판정했습니다/);
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
    expect(screen.getByRole("button", { name: "오류 있음" }).getAttribute("aria-keyshortcuts")).toBe("1");
    expect(screen.getByRole("button", { name: "오류 없음" }).getAttribute("aria-keyshortcuts")).toBe("2");
    expect(screen.getByRole("button", { name: "판단 보류" }).getAttribute("aria-keyshortcuts")).toBe("3");
    expect(screen.getByRole("button", { name: "이전" }).getAttribute("aria-keyshortcuts")).toBe("ArrowLeft");
    expect(screen.getByRole("button", { name: "다음" }).getAttribute("aria-keyshortcuts")).toBe("ArrowRight");
  });
});

describe("선택 표시", () => {
  test("고른 판정만 aria-pressed가 참이고, 판정 취소하면 모두 거짓이다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand(), cand({ canonical_candidate_id: "B" })]));
    show();
    await screen.findByText("a.jpg");
    for (const name of ["오류 있음", "오류 없음", "판단 보류"]) {
      expect(screen.getByRole("button", { name }).getAttribute("aria-pressed")).toBe("false");
    }

    await act(async () => screen.getByRole("button", { name: "오류 없음" }).click());
    // 저장되면 B로 넘어간다. 돌아가면 고른 판정이 눌려 있다.
    await screen.findByText(/앞 후보 저장됨/);
    expect(pressed()).toEqual([]);
    await press("ArrowLeft");
    expect(screen.getByRole("button", { name: "오류 없음" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "오류 있음" }).getAttribute("aria-pressed")).toBe("false");

    await act(async () => screen.getByRole("button", { name: "판정 취소" }).click());
    expect(pressed()).toEqual([]);
    // 판정 취소는 옮기지 않는다.
    await screen.findByText("저장됨");
    expect(screen.getByText("후보 1 / 2")).toBeTruthy();
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
    expect(screen.getByRole("button", { name: "오류 있음" })).toBeTruthy();
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

    await act(async () => screen.getByRole("button", { name: "판단 보류" }).click());
    expect(bar.value).toBe(2);
    screen.getByText("2 / 4 판정 (남은 2)");
  });

  test("저장 상태를 저장 중·저장됨·저장 실패로 가른다", async () => {
    let release!: (v: unknown) => void;
    putAdjudications.mockReturnValueOnce(new Promise((r) => (release = r)));
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    getBlindQueue.mockResolvedValue(queue([
      cand({ canonical_candidate_id: "A" }),
      cand({ canonical_candidate_id: "B", image: "b.jpg" }),
    ]));
    show();
    await screen.findByText("a.jpg");

    await act(async () => screen.getByRole("button", { name: "오류 있음" }).click());
    expect(screen.getByText("저장 중…").className).toMatch(/save-saving/);
    await act(async () => release({}));
    // 저장되면 다음 후보로 넘어오고, "저장됨"이 아니라 "앞 후보 저장됨"이라고 말한다.
    expect((await screen.findByText(/^앞 후보 저장됨/)).className).toMatch(/save-advanced/);
    screen.getByText("b.jpg");

    await act(async () => screen.getByRole("button", { name: "판단 보류" }).click());
    expect((await screen.findByText(/^저장 실패/)).className).toMatch(/save-failed/);
    screen.getByText("b.jpg");

    // 옮기지 않는 저장(판정 취소)은 "저장됨"이다.
    await act(async () => screen.getByRole("button", { name: "판정 취소" }).click());
    expect((await screen.findByText("저장됨")).className).toMatch(/save-saved/);
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

describe("튜토리얼 접근성", () => {
  test("떠 있는 동안 뒤 화면은 inert이고, 닫으면 풀린다", async () => {
    localStorage.removeItem(TUTORIAL_KEY);
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByRole("dialog");
    const body = document.querySelector(".judge-body")!;
    // 뒤의 판정 단추가 Tab·Enter로 눌리지 않게 막는다.
    expect(body.hasAttribute("inert")).toBe(true);
    expect(body.contains(screen.getByRole("dialog"))).toBe(false);

    await act(async () => screen.getByRole("button", { name: "건너뛰기" }).click());
    expect(body.hasAttribute("inert")).toBe(false);
  });

  test("Tab이 대화 상자 안에서 돈다", async () => {
    localStorage.removeItem(TUTORIAL_KEY);
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    const dialog = await screen.findByRole("dialog");
    const skip = screen.getByRole("button", { name: "건너뛰기" });
    const next = screen.getByRole("button", { name: "다음 단계" });
    expect(document.activeElement).toBe(next);

    // 마지막 단추에서 Tab → 첫 단추, 첫 단추에서 Shift+Tab → 마지막 단추.
    fireEvent.keyDown(next, { key: "Tab" });
    expect(document.activeElement).toBe(skip);
    fireEvent.keyDown(skip, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(next);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  test("다시 보기로 열었다 닫으면 그 단추로 초점이 돌아간다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");
    const opener = screen.getByRole("button", { name: "튜토리얼 다시 보기" });
    opener.focus();
    await act(async () => opener.click());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "다음 단계" }));

    await press("Escape");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});

describe("저장 상태 안내", () => {
  test("옮기면 '저장됨'이 다음 후보에 따라가지 않고, 판정한 후보로 돌아오면 저장돼 있다고 말한다", async () => {
    getBlindQueue.mockResolvedValue(queue([
      cand({ canonical_candidate_id: "A" }),
      cand({ canonical_candidate_id: "B", image: "b.jpg" }),
    ]));
    show();
    await screen.findByText("a.jpg");
    screen.getByText("판정을 누르면 바로 저장되고 다음 후보로 넘어갑니다.");

    await act(async () => screen.getByRole("button", { name: "오류 있음" }).click());
    await screen.findByText("b.jpg");
    // 넘어온 후보에는 "저장됨"이 따라오지 않는다 — 앞 후보가 저장됐다고만 말한다.
    expect(screen.queryByText("저장됨")).toBeNull();
    screen.getByText(/앞 후보 저장됨/);

    await press("ArrowLeft");
    await screen.findByText("a.jpg");
    screen.getByText("이 후보의 판정은 저장되어 있습니다.");

    await press("ArrowRight");
    await screen.findByText("b.jpg");
    screen.getByText("판정을 누르면 바로 저장되고 다음 후보로 넘어갑니다.");
    // 화면 표시만 바꿨다 — 저장은 처음 한 번뿐이다.
    expect(putAdjudications).toHaveBeenCalledTimes(1);
  });

  test("저장 실패는 옮겨도 남아 다시 시도할 수 있다", async () => {
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    getBlindQueue.mockResolvedValue(queue([
      cand({ canonical_candidate_id: "A" }),
      cand({ canonical_candidate_id: "B", image: "b.jpg" }),
    ]));
    show();
    await screen.findByText("a.jpg");
    await act(async () => screen.getByRole("button", { name: "오류 있음" }).click());
    await screen.findByText(/^저장 실패/);

    await press("ArrowRight");
    await screen.findByText("b.jpg");
    screen.getByText(/^저장 실패/);
    screen.getByRole("button", { name: "다시 시도" });
  });
});

describe("후보 위치", () => {
  test("몇 번째 후보인지 보여 준다", async () => {
    getBlindQueue.mockResolvedValue(queue([
      cand({ canonical_candidate_id: "A", verdict: "hit" }),
      cand({ canonical_candidate_id: "B", image: "b.jpg" }),
    ]));
    show();
    await screen.findByText("b.jpg");
    screen.getByText("후보 2 / 2");
  });

  test("누락 오류에서 어느 객체인지 고르는 법을 적는다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand({ label_index: null })]));
    show();
    await screen.findByText("a.jpg");
    await act(async () => screen.getByRole("button", { name: "오류 있음" }).click());
    expect(document.querySelector(".missing-hint")?.textContent).toMatch(/같은 차.*새 객체/);
  });
});
