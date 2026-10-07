/**
 * 가림 판정 화면 — 단추 글자↔저장값 대응과 저장 뒤 자동 이동.
 *
 * **대응이 뒤집히면 판정 전체가 뒤집힌다.** 질문 문구를 바꿨으니(“수정이 필요한가?”·“누락됐는가?”) 두 층 모두
 * "오류 있음 = hit · 오류 없음 = miss · 판단 보류 = hold"인지, 서버에 이미 있는 판정이 같은 단추로 눌려
 * 보이는지를 고정한다.
 *
 * 자동 이동은 **저장이 성공한 뒤에만** 일어난다. 실패하면 남고, 누락 오류는 객체 번호까지 정해 저장돼야
 * 넘어간다. 저장 중의 연타·StrictMode의 두 번 실행이 저장·이동을 두 번 만들지 않는지도 본다.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act, StrictMode } from "react";

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
import { QUESTION_EXISTING, QUESTION_MISSING, VERDICT_BUTTONS } from "./blindAdjudicationLogic";

const DS = "0123456789ab";
const EVAL = "e1";

function cand(id: string, over: Record<string, unknown> = {}) {
  return {
    canonical_candidate_id: id,
    image: `${id.toLowerCase()}.jpg`,
    label_index: 0,
    box: [1, 2, 3, 4],
    verdict: null,
    unique_error_id: null,
    ...over,
  };
}

function queue(candidates: unknown[]) {
  return { evaluation_id: EVAL, dataset_id: DS, candidate_set_hash: "h1", candidates, damaged: false };
}

function show(strict = false) {
  const ui = <BlindAdjudication datasetId={DS} evaluationId={EVAL} />;
  return render(strict ? <StrictMode>{ui}</StrictMode> : ui);
}

async function click(name: string) {
  await act(async () => screen.getAllByRole("button", { name })[0].click());
}

async function press(key: string) {
  await act(async () => {
    fireEvent.keyDown(document.body, { key });
  });
}

function logged() {
  return postActivity.mock.calls.flatMap((call) => call[3] as Array<{
    event: string; canonical_candidate_id: string | null; meta: Record<string, unknown>;
  }>);
}
const autoMoves = () => logged().filter((e) => e.event === "moved_next" && e.meta?.auto === true);

const pressed = () =>
  screen.getAllByRole("button")
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.textContent);

/** 지금 띄운 후보의 이미지 이름. */
const shown = () => document.querySelector(".judge-meta span:last-child")?.textContent;

beforeEach(() => {
  getBlindQueue.mockReset();
  putAdjudications.mockReset();
  putAdjudications.mockResolvedValue({});
  postActivity.mockReset();
  postActivity.mockResolvedValue({});
  localStorage.clear();
  localStorage.setItem(TUTORIAL_KEY, "done");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("단추 글자와 저장값", () => {
  test("대응표 — 오류 있음=hit(1) · 오류 없음=miss(2) · 판단 보류=hold(3)", () => {
    expect(VERDICT_BUTTONS.map((b) => [b.label, b.verdict, b.key])).toEqual([
      ["오류 있음", "hit", "1"],
      ["오류 없음", "miss", "2"],
      ["판단 보류", "hold", "3"],
    ]);
  });

  test("질문은 층마다 정해진 문구다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("M", { label_index: null })]));
    show();
    await screen.findByText(QUESTION_EXISTING);
    expect(QUESTION_EXISTING).toBe("이 라벨은 수정이 필요한가?");
    await press("ArrowRight");
    await screen.findByText(QUESTION_MISSING);
    expect(QUESTION_MISSING).toBe("이 객체의 라벨이 누락됐는가?");
  });

  for (const layer of ["existing", "missing"] as const) {
    const over = layer === "missing" ? { label_index: null } : {};
    for (const { label, verdict, key } of VERDICT_BUTTONS) {
      for (const how of ["click", "key"] as const) {
        test(`${layer === "missing" ? "누락" : "기존 라벨"}: ${how === "key" ? `키 ${key}` : `"${label}" 클릭`} → ${verdict}`, async () => {
          getBlindQueue.mockResolvedValue(queue([cand("A", over), cand("B")]));
          show();
          await screen.findByText("a.jpg");
          if (how === "key") await press(key);
          else await click(label);
          if (layer === "missing" && verdict === "hit") {
            // 누락 오류는 객체 번호를 정해야 저장된다.
            expect(pressed()).toEqual([label]);
            expect(putAdjudications).not.toHaveBeenCalled();
            await click("새 객체");
          }
          await waitFor(() => expect(putAdjudications).toHaveBeenCalledTimes(1));
          const row = putAdjudications.mock.calls[0][3].find(
            (r: { canonical_candidate_id: string }) => r.canonical_candidate_id === "A");
          expect(row.verdict).toBe(verdict);
          expect(row.unique_error_id).toBe(layer === "missing" && verdict === "hit" ? "M1" : null);
          // 저장 뒤 넘어갔다. 돌아가면 같은 단추가 눌려 있다.
          await screen.findByText("b.jpg");
          await press("ArrowLeft");
          expect(pressed().filter((t) => t !== "M1")).toEqual([label]);
        });
      }
    }
  }

  test("서버에 있던 판정이 같은 뜻의 단추로 눌려 보인다(두 층 모두)", async () => {
    getBlindQueue.mockResolvedValue(queue([
      cand("H", { verdict: "hit" }),
      cand("S", { verdict: "miss" }),
      cand("D", { verdict: "hold" }),
      cand("MH", { label_index: null, verdict: "hit", unique_error_id: "mh.jpg/M1" }),
      cand("MS", { label_index: null, verdict: "miss" }),
      cand("MD", { label_index: null, verdict: "hold" }),
      cand("Z"),
    ]));
    show();
    await screen.findByText("z.jpg");
    const seen: Array<[string | null | undefined, Array<string | null>]> = [];
    const back = async () => {
      await press("ArrowLeft");
      seen.unshift([shown(), pressed().filter((t) => t !== "M1")]);
    };
    await back();
    await back();
    await back();
    await back();
    await back();
    await back();
    expect(seen).toEqual([
      ["h.jpg", ["오류 있음"]],
      ["s.jpg", ["오류 없음"]],
      ["d.jpg", ["판단 보류"]],
      ["mh.jpg", ["오류 있음"]],
      ["ms.jpg", ["오류 없음"]],
      ["md.jpg", ["판단 보류"]],
    ]);
    // 돌아보기만 했다 — 저장은 없다.
    expect(putAdjudications).not.toHaveBeenCalled();
  });
});

describe("저장 뒤 자동 이동", () => {
  test("저장이 성공하면 다음 미판정 후보로 넘어가고 moved_next(auto)를 남긴다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B", { verdict: "hit" }), cand("C")]));
    const { unmount } = show();
    await screen.findByText("a.jpg");

    await click("오류 있음");
    await screen.findByText("c.jpg");          // 이미 판정한 B는 건너뛴다
    await act(async () => unmount());

    const moves = autoMoves();
    expect(moves).toHaveLength(1);
    expect(moves[0].canonical_candidate_id).toBeNull();
    // 순서: 판정 → 저장 시작 → 저장 성공 → 이동 → 다음 후보 열기
    const names = logged().map((e) => e.event);
    const at = (n: string, from = 0) => names.indexOf(n, from);
    expect(at("save_succeeded")).toBeGreaterThan(at("save_started"));
    expect(at("moved_next")).toBeGreaterThan(at("save_succeeded"));
    expect(names.lastIndexOf("candidate_opened")).toBeGreaterThan(at("moved_next"));
  });

  test("뒤에 미판정이 없으면 앞에서 찾는다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B", { verdict: "miss" }), cand("C")]));
    show();
    await screen.findByText("a.jpg");
    await click("다음 미판정 (2)");           // C로
    await screen.findByText("c.jpg");
    await click("오류 없음");
    await screen.findByText("a.jpg");
  });

  test("마지막 미판정을 저장하면 완료 화면이 뜬다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A")]));
    show();
    await screen.findByText("a.jpg");
    await click("오류 없음");
    await screen.findByText(/모두 판정했습니다/);
  });

  test("저장에 실패하면 그 후보에 남는다", async () => {
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B")]));
    const { unmount } = show();
    await screen.findByText("a.jpg");

    await click("오류 있음");
    await screen.findByText(/^저장 실패/);
    expect(shown()).toBe("a.jpg");
    expect(pressed()).toEqual(["오류 있음"]);
    await act(async () => unmount());
    expect(autoMoves()).toHaveLength(0);
  });

  test("누락 오류는 객체 번호를 고르고 그 저장이 성공해야 넘어간다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A", { label_index: null }), cand("B")]));
    show();
    await screen.findByText("a.jpg");

    await click("오류 있음");
    expect(putAdjudications).not.toHaveBeenCalled();
    expect(shown()).toBe("a.jpg");             // 번호 전에는 안 넘어간다

    let release!: (v: unknown) => void;
    putAdjudications.mockReturnValueOnce(new Promise((r) => (release = r)));
    await click("새 객체");
    expect(shown()).toBe("a.jpg");             // 저장 응답 전에도 안 넘어간다
    await act(async () => release({}));
    await screen.findByText("b.jpg");
    expect(putAdjudications.mock.calls[0][3][0]).toMatchObject({ verdict: "hit", unique_error_id: "M1" });
  });

  test("누락 오류의 번호 저장이 실패하면 남는다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A", { label_index: null }), cand("B")]));
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    show();
    await screen.findByText("a.jpg");
    await click("오류 있음");
    await click("새 객체");
    await screen.findByText(/^저장 실패/);
    expect(shown()).toBe("a.jpg");
  });

  test("판단 보류도 저장되면 넘어간다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B")]));
    show();
    await screen.findByText("a.jpg");
    await press("3");
    await screen.findByText("b.jpg");
    expect(putAdjudications.mock.calls[0][3][0]).toMatchObject({ verdict: "hold" });
  });

  test("판정 취소는 넘어가지 않는다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A", { verdict: "hit" }), cand("B")]));
    show();
    await screen.findByText("b.jpg");
    await press("ArrowLeft");
    await click("판정 취소");
    await screen.findByText("저장됨");
    expect(shown()).toBe("a.jpg");
  });

  test("이전으로 돌아가 판정을 바꾸면 저장 뒤 다음 미판정으로 간다", async () => {
    getBlindQueue.mockResolvedValue(queue([
      cand("A", { verdict: "hit" }), cand("B", { verdict: "miss" }), cand("C"), cand("D"),
    ]));
    show();
    await screen.findByText("c.jpg");
    await press("ArrowLeft");
    await press("ArrowLeft");
    expect(shown()).toBe("a.jpg");

    await click("판단 보류");                  // hit → hold
    await screen.findByText("c.jpg");          // A 다음의 첫 미판정
    expect(putAdjudications).toHaveBeenCalledTimes(1);
    const rows = putAdjudications.mock.calls[0][3];
    expect(rows.find((r: { canonical_candidate_id: string }) =>
      r.canonical_candidate_id === "A").verdict).toBe("hold");
  });

  test("전부 판정한 뒤 돌아가 바꾸면 저장 뒤 완료 화면으로 간다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A", { verdict: "hit" }), cand("B", { verdict: "miss" })]));
    show();
    await screen.findByText(/모두 판정했습니다/);
    await click("처음부터 다시 보기");
    await click("오류 없음");
    await screen.findByText(/모두 판정했습니다/);
    expect(putAdjudications).toHaveBeenCalledTimes(1);
  });

  test("저장 응답 전에 직접 옮겼으면 응답이 와도 한 번 더 옮기지 않는다", async () => {
    let release!: (v: unknown) => void;
    putAdjudications.mockReturnValueOnce(new Promise((r) => (release = r)));
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B"), cand("C")]));
    const { unmount } = show();
    await screen.findByText("a.jpg");
    await click("오류 있음");
    await press("ArrowRight");
    expect(shown()).toBe("b.jpg");
    await act(async () => release({}));
    expect(shown()).toBe("b.jpg");
    await act(async () => unmount());
    expect(autoMoves()).toHaveLength(0);
  });
});

describe("중복 입력", () => {
  test("저장 중 연타·키 반복은 무시된다 — 저장 한 번, 이동 한 번", async () => {
    let release!: (v: unknown) => void;
    putAdjudications.mockReturnValueOnce(new Promise((r) => (release = r)));
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B"), cand("C")]));
    const { unmount } = show();
    await screen.findByText("a.jpg");

    await act(async () => {
      fireEvent.keyDown(document.body, { key: "1" });
      fireEvent.keyDown(document.body, { key: "1" });
      fireEvent.keyDown(document.body, { key: "2" });
    });
    await click("오류 있음");
    await click("판단 보류");
    expect(putAdjudications).toHaveBeenCalledTimes(1);

    await act(async () => release({}));
    await screen.findByText("b.jpg");
    expect(putAdjudications).toHaveBeenCalledTimes(1);
    expect(putAdjudications.mock.calls[0][3][0]).toMatchObject({ canonical_candidate_id: "A", verdict: "hit" });
    await act(async () => unmount());
    expect(autoMoves()).toHaveLength(1);
    expect(logged().filter((e) => e.event === "verdict_set")).toHaveLength(1);
  });

  test("StrictMode에서도 저장 한 번, 이동 한 번이다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B"), cand("C")]));
    const { unmount } = show(true);
    await screen.findByText("a.jpg");

    await click("오류 있음");
    await screen.findByText("b.jpg");
    expect(putAdjudications).toHaveBeenCalledTimes(1);
    await act(async () => unmount());
    expect(autoMoves()).toHaveLength(1);
    const opened = logged().filter((e) => e.event === "candidate_opened")
      .map((e) => e.canonical_candidate_id);
    expect(opened).toEqual(["A", "B"]);
  });
});

describe("전체 이미지 보기가 떠 있을 때", () => {
  test("판정·이동 단축키를 무시한다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand("A"), cand("B")]));
    show();
    await screen.findByText("a.jpg");
    // AdjudicationView의 전체 보기 대화 상자 대신 같은 표시(aria-modal)를 단다.
    const modal = document.createElement("div");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    document.body.append(modal);
    await press("1");
    await press("ArrowRight");
    modal.remove();
    expect(putAdjudications).not.toHaveBeenCalled();
    expect(shown()).toBe("a.jpg");
  });
});
