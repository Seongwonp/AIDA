/**
 * 가림 판정 화면의 묶음 표시 (사전 등록 D5·D6, 개정 5).
 *
 * 기존 라벨 묶음들 → 누락 묶음. 머리글은 "기존 라벨 묶음 2/4 · 37/96"처럼 층·묶음·묶음 안 위치만 보인다.
 * 자동 이동·이전/다음·"다음 미판정"은 묶음 안에서만 움직이고, 묶음이 다 차면 묶음 완료 화면(쉬어도 되는
 * 자리)에서 멈춘다. 다음 묶음은 "다음 묶음 시작"을 눌러야 시작한다. 저장이 실패하면 그 후보에 남는다.
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
import { BUNDLE_MISMATCH_MESSAGE, QUESTION_MISSING } from "./blindAdjudicationLogic";

const DS = "0123456789ab";
const EVAL = "inspect_x";

function cand(id: string, bundle: number, over: Record<string, unknown> = {}) {
  return {
    canonical_candidate_id: id,
    image: `${id.toLowerCase()}.jpg`,
    label_index: 0,
    box: [1, 2, 3, 4],
    verdict: null,
    unique_error_id: null,
    bundle,
    ...over,
  };
}
const miss = (id: string, bundle: number, over: Record<string, unknown> = {}) =>
  cand(id, bundle, { label_index: null, ...over });

const BUNDLES = [
  { index: 0, layer: "labelled_candidates", layer_bundle: 1, layer_bundles: 2, size: 2 },
  { index: 1, layer: "labelled_candidates", layer_bundle: 2, layer_bundles: 2, size: 2 },
  { index: 2, layer: "missing_candidates", layer_bundle: 1, layer_bundles: 1, size: 2 },
];

/** A,B | C,D | M,N — 판정 상태만 덮어쓴다. */
function queue(verdicts: Record<string, string> = {}) {
  const v = (id: string) => (verdicts[id] ? { verdict: verdicts[id] } : {});
  return {
    evaluation_id: EVAL, dataset_id: DS, candidate_set_hash: "h1", damaged: false,
    bundles: BUNDLES,
    candidates: [
      cand("A", 0, v("A")), cand("B", 0, v("B")), cand("C", 1, v("C")), cand("D", 1, v("D")),
      miss("M", 2, v("M")), miss("N", 2, v("N")),
    ],
  };
}

const show = () => render(<BlindAdjudication datasetId={DS} evaluationId={EVAL} />);
const shown = () => document.querySelector(".judge-meta span:last-child")?.textContent ?? null;
const header = () => document.querySelector(".judge-position")?.textContent ?? null;

async function click(name: string | RegExp) {
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

describe("묶음 머리글", () => {
  test("층·묶음·묶음 안 위치만 보인다", async () => {
    getBlindQueue.mockResolvedValue(queue());
    show();
    await screen.findByText("a.jpg");
    expect(header()).toBe("기존 라벨 묶음 1/2 · 1/2");
    await press("ArrowRight");
    expect(header()).toBe("기존 라벨 묶음 1/2 · 2/2");
    // 묶음 이동 단추에는 진행 수만(판정 결과 요약 없음).
    expect(screen.getByRole("navigation", { name: "묶음 이동" }).textContent)
      .toBe("기존 라벨 묶음 1/2 (0/2)기존 라벨 묶음 2/2 (0/2)누락 묶음 (0/2)");
  });

  test("묶음 표가 목록과 어긋나면 판정을 받지 않는다", async () => {
    const bad = queue();
    bad.candidates[1] = cand("B", 1);
    getBlindQueue.mockResolvedValue(bad);
    show();
    await screen.findByText(BUNDLE_MISMATCH_MESSAGE);
    expect(screen.queryAllByRole("button", { name: "오류 있음" })).toHaveLength(0);
  });
});

describe("묶음 경계", () => {
  test("이전·다음은 묶음 밖으로 나가지 않는다", async () => {
    getBlindQueue.mockResolvedValue(queue({ A: "miss", B: "miss" }));
    show();
    await screen.findByText("c.jpg");
    await press("ArrowLeft");                  // 묶음 2의 첫 후보 — 앞 묶음으로 안 간다
    expect(shown()).toBe("c.jpg");
    await press("ArrowRight");
    await press("ArrowRight");                 // 묶음 끝 — 누락 묶음으로 안 간다
    expect(shown()).toBe("d.jpg");
  });

  test("자동 이동은 묶음 끝에서 멈추고 묶음 완료 화면을 띄운다", async () => {
    getBlindQueue.mockResolvedValue(queue());
    const { unmount } = show();
    await screen.findByText("a.jpg");
    await click("오류 있음");
    await screen.findByText("b.jpg");
    await click("오류 없음");
    await screen.findByText(/기존 라벨 묶음 1\/2 판정을 마쳤습니다 \(2건\)\. 여기서 쉬어도 됩니다/);
    expect(shown()).toBeNull();               // 다음 묶음의 후보를 띄우지 않는다
    expect(screen.queryByText(/모두 판정했습니다/)).toBeNull();
    await act(async () => unmount());
    const last = logged().filter((e) => e.event === "moved_next").at(-1);
    expect(last?.meta).toEqual({ auto: true, bundle_complete: 0 });
    expect(logged().filter((e) => e.event === "candidate_opened").map((e) => e.canonical_candidate_id))
      .toEqual(["A", "B"]);
  });

  test("묶음 완료 화면에서 다음 묶음을 시작하면 그 묶음의 첫 미판정으로 간다", async () => {
    getBlindQueue.mockResolvedValue(queue({ A: "miss", D: "hit" }));
    const { unmount } = show();
    await screen.findByText("b.jpg");
    await click("판단 보류");
    await screen.findByText(/판정을 마쳤습니다/);
    await click("다음 묶음 시작 — 기존 라벨 묶음 2/2");
    await screen.findByText("c.jpg");
    expect(header()).toBe("기존 라벨 묶음 2/2 · 1/2");
    await act(async () => unmount());
    const start = logged().filter((e) => e.event === "moved_next").at(-1);
    expect(start?.meta).toEqual({ bundle_start: 1 });
  });

  test("누락 묶음 앞에서는 질문이 바뀐다고 알린다", async () => {
    getBlindQueue.mockResolvedValue(queue({ A: "miss", B: "miss", C: "miss" }));
    show();
    await screen.findByText("d.jpg");
    await click("오류 없음");
    await screen.findByText(/다음은 누락 묶음입니다/);
    await click("다음 묶음 시작 — 누락 묶음");
    await screen.findByText(QUESTION_MISSING);
    expect(header()).toBe("누락 묶음 · 1/2");
  });

  test("저장이 실패하면 묶음 끝 후보에 남고 묶음 완료 화면을 띄우지 않는다", async () => {
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    getBlindQueue.mockResolvedValue(queue({ A: "miss" }));
    show();
    await screen.findByText("b.jpg");
    await click("오류 있음");
    await screen.findByText(/^저장 실패/);
    expect(shown()).toBe("b.jpg");
    expect(screen.queryByText(/판정을 마쳤습니다/)).toBeNull();
    // 다시 시도가 성공하면 그때 묶음 완료 화면으로 간다.
    await click("다시 시도");
    await screen.findByText(/기존 라벨 묶음 1\/2 판정을 마쳤습니다/);
  });

  test("마지막 묶음을 마치면 기존 완료 화면이 뜬다", async () => {
    getBlindQueue.mockResolvedValue(queue({ A: "miss", B: "miss", C: "miss", D: "miss", M: "miss" }));
    show();
    await screen.findByText("n.jpg");
    await click("오류 없음");
    await screen.findByText(/모두 판정했습니다/);
    expect(screen.queryByText(/다음 묶음 시작/)).toBeNull();
  });

  test("다음 미판정은 지금 묶음 안의 미판정만 센다", async () => {
    getBlindQueue.mockResolvedValue(queue());
    show();
    await screen.findByText("a.jpg");
    expect(screen.getByRole("button", { name: "다음 미판정 (2)" })).toBeTruthy();
  });
});

describe("재개와 앞 묶음 고치기", () => {
  test("재개 — 미판정이 남은 가장 앞 묶음의 첫 미판정에서", async () => {
    getBlindQueue.mockResolvedValue(queue({ B: "miss", C: "miss" }));
    show();
    await screen.findByText("a.jpg");
    expect(header()).toBe("기존 라벨 묶음 1/2 · 1/2");
  });

  test("재개 — 앞 묶음이 다 찼으면 묶음 완료 화면 없이 다음 묶음에서", async () => {
    getBlindQueue.mockResolvedValue(queue({ A: "miss", B: "hit", C: "hold", D: "miss" }));
    show();
    await screen.findByText("m.jpg");
    expect(header()).toBe("누락 묶음 · 1/2");
    expect(screen.queryByText(/판정을 마쳤습니다/)).toBeNull();
  });

  test("앞 묶음으로 돌아가 고칠 수 있고, 아직 시작 안 한 뒤 묶음으로는 건너뛰지 않는다", async () => {
    getBlindQueue.mockResolvedValue(queue({ A: "miss", B: "miss" }));
    show();
    await screen.findByText("c.jpg");
    const chip = (name: RegExp) => screen.getByRole("button", { name });
    expect((chip(/^누락 묶음/) as HTMLButtonElement).disabled).toBe(true);
    await click(/^기존 라벨 묶음 1\/2/);
    expect(shown()).toBe("a.jpg");             // 다 판정한 묶음은 첫 후보로
    await click("오류 있음");                  // miss → hit, 저장 뒤 그 묶음은 이미 찼다
    await screen.findByText(/기존 라벨 묶음 1\/2 판정을 마쳤습니다/);
    await click("다음 묶음 시작 — 기존 라벨 묶음 2/2");
    await screen.findByText("c.jpg");
    await waitFor(() => expect(putAdjudications).toHaveBeenCalledTimes(1));
    const rows = putAdjudications.mock.calls[0][3];
    expect(rows.find((r: { canonical_candidate_id: string }) => r.canonical_candidate_id === "A").verdict)
      .toBe("hit");
    const back = logged().find((e) => e.event === "moved_previous");
    expect(back?.meta).toEqual({ bundle: 0 });
  });
});

describe("묶음이 없는 옛 묶음", () => {
  test("머리글은 예전 그대로 '후보 n / 전체'이고 묶음 단추가 없다", async () => {
    const old = queue();
    getBlindQueue.mockResolvedValue({
      ...old, bundles: undefined,
      candidates: old.candidates.map(({ bundle: _b, ...rest }) => rest),
    });
    show();
    await screen.findByText("a.jpg");
    expect(header()).toBe("후보 1 / 6");
    expect(screen.queryByRole("navigation", { name: "묶음 이동" })).toBeNull();
  });
});
