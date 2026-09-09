/**
 * 가림 판정 화면의 실제 흐름 (docs/evaluation-adjudication-design.md).
 *
 * 순수 함수 검사는 규칙만 고정한다. **화면이 그 규칙대로 도는지**는 상태 갱신
 * 순서에 달려 있어 실제 React로만 확인할 수 있다 — R1에서 초기 조회가 신규
 * 판정을 덮어쓰던 것이 그런 자리였다.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";

const getBlindQueue = vi.fn();
const putAdjudications = vi.fn();
vi.mock("../api", () => ({
  getBlindQueue: (...a: unknown[]) => getBlindQueue(...a),
  putAdjudications: (...a: unknown[]) => putAdjudications(...a),
  API_BASE_URL: "",
}));
// 미리보기는 이 검사와 무관하고 이미지를 부른다.
vi.mock("./BoxPreview", () => ({ BoxPreview: () => null }));

import { BlindAdjudication } from "./BlindAdjudication";

const DS = "0123456789ab";
const EVAL = "e1";

type Cand = {
  canonical_candidate_id: string;
  image: string;
  label_index: number | null;
  box: number[] | null;
  verdict: "hit" | "miss" | "hold" | null;
  unique_error_id: string | null;
};

function cand(over: Partial<Cand> = {}): Cand {
  return {
    canonical_candidate_id: "La1b2c3",
    image: "a.jpg",
    label_index: 0,
    box: [1, 2, 3, 4],
    verdict: null,
    unique_error_id: null,
    ...over,
  };
}

function queue(candidates: Cand[], over: Record<string, unknown> = {}) {
  return {
    evaluation_id: EVAL,
    dataset_id: DS,
    candidate_set_hash: "h1",
    candidates,
    damaged: false,
    ...over,
  };
}

function show() {
  return render(<BlindAdjudication datasetId={DS} evaluationId={EVAL} />);
}

async function click(name: string) {
  const button = screen.getAllByRole("button", { name })[0];
  await act(async () => {
    button.click();
  });
}

beforeEach(() => {
  getBlindQueue.mockReset();
  putAdjudications.mockReset();
  putAdjudications.mockResolvedValue({});
});

afterEach(cleanup);

describe("가림", () => {
  test("점수·순위·의심 유형이 화면에 없다", async () => {
    // 후보 이름 자체가 유형을 담고 있던 적이 있다 — 서버에서 고쳤지만,
    // 화면이 다시 흘리지 않는지 여기서도 잡는다.
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");

    // 안내 문구에는 "순위·점수를 가린다"는 설명이 있으므로 **후보 영역만** 본다.
    const article = document.querySelector("article");
    expect(article?.textContent ?? "").not.toMatch(
      /width|scale|missing|severity|순위|점수|\d+위/);
  });

  test("후보에 붙은 어떤 속성도 유형이나 점수를 담지 않는다", () => {
    // 화면 문구를 지워도 DOM 속성이나 title로 새면 판정자가 보게 된다.
    const cands = [cand()];
    const fields = Object.keys(cands[0]);
    expect(fields).not.toContain("suspicion");
    expect(fields).not.toContain("severity");
    expect(fields).not.toContain("rank");
    expect(fields).not.toContain("detail");
  });
});

describe("버튼 자리", () => {
  test("저장 상태와 경고가 판정 버튼보다 아래에 있다", async () => {
    // 위에 있으면 판정할 때마다 문구가 생겨 버튼이 아래로 밀린다. 연달아
    // 누르는 사람이 엉뚱한 버튼을 누르게 되고, 브라우저 확인에서 실제로 그랬다.
    //
    // jsdom에는 배치가 없어 "밀렸다"를 직접 잴 수 없다. 대신 밀림을 막는
    // **문서 순서**를 고정한다 — 상태 문구가 버튼 뒤에 있으면 위쪽이 안 변한다.
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    const button = await screen.findByRole("button", { name: "오류였다" });
    const status = document.querySelector("[aria-live]")!;

    expect(button.compareDocumentPosition(status))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    // 저장에 실패해 "다시 시도"가 생겨도 마찬가지다.
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    await click("오류였다");
    const retry = await screen.findByRole("button", { name: "다시 시도" });
    expect(button.compareDocumentPosition(retry))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });
});

describe("판정 저장", () => {
  test("판정하면 곧바로 보낸다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    show();
    await screen.findByText("a.jpg");

    await click("오류였다");

    await waitFor(() => expect(putAdjudications).toHaveBeenCalled());
    const [, , hash, rows] = putAdjudications.mock.calls[0];
    expect(hash).toBe("h1");
    expect(rows[0]).toMatchObject({
      canonical_candidate_id: "La1b2c3",
      verdict: "hit",
      unique_error_id: null,       // 기존 라벨은 서버가 정한다
    });
  });

  test("판정을 취소하면 취소도 보낸다", async () => {
    // 안 보내면 서버에 옛 판정이 남아 화면과 어긋난다.
    getBlindQueue.mockResolvedValue(queue([cand({ verdict: "hit" })]));
    show();
    await screen.findByText("a.jpg");

    await click("판정 취소");

    await waitFor(() => expect(putAdjudications).toHaveBeenCalled());
    const rows = putAdjudications.mock.calls.at(-1)![3];
    expect(rows[0].verdict).toBeNull();
  });

  test("저장에 실패하면 알리고, 다시 시도가 통한다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    putAdjudications.mockRejectedValueOnce(new Error("끊김"));
    show();
    await screen.findByText("a.jpg");

    await click("오류였다");
    await screen.findByText(/저장하지 못했습니다/);

    await click("다시 시도");
    await waitFor(() => expect(putAdjudications).toHaveBeenCalledTimes(2));
    await screen.findByText("저장됨");
  });
});

describe("누락 객체", () => {
  const missing = [
    cand({ canonical_candidate_id: "Cm1", image: "a.jpg", label_index: null }),
    cand({ canonical_candidate_id: "Cm2", image: "a.jpg", label_index: null }),
  ];

  test("객체를 안 정하면 보내지 않고 이유를 말한다", async () => {
    getBlindQueue.mockResolvedValue(queue(missing));
    show();
    await screen.findByText("a.jpg");

    await click("오류였다");

    expect(putAdjudications).not.toHaveBeenCalled();
    await screen.findByText(/어느 객체인지 골라야/);
  });

  test("새 객체를 만들면 그때 보낸다", async () => {
    getBlindQueue.mockResolvedValue(queue(missing));
    show();
    await screen.findByText("a.jpg");

    await click("오류였다");
    await click("새 객체");

    await waitFor(() => expect(putAdjudications).toHaveBeenCalled());
    const rows = putAdjudications.mock.calls.at(-1)![3];
    expect(rows.find((r: { canonical_candidate_id: string }) =>
      r.canonical_candidate_id === "Cm1").unique_error_id).toBe("M1");
  });

  test("겹쳐 잡은 둘을 한 객체로 이을 수 있다", async () => {
    // 이을 방법이 없으면 고유 오류 수가 부풀려진다.
    getBlindQueue.mockResolvedValue(queue(missing));
    show();
    await screen.findByText("a.jpg");

    await click("오류였다");
    await click("새 객체");
    await click("다음");
    await click("오류였다");
    await click("M1");

    const rows = putAdjudications.mock.calls.at(-1)![3];
    const ids = rows
      .filter((r: { verdict: string }) => r.verdict === "hit")
      .map((r: { unique_error_id: string }) => r.unique_error_id);
    expect(ids).toEqual(["M1", "M1"]);
  });

  test("오류가 아니라고 바꾸면 붙여 둔 객체를 뗀다", async () => {
    getBlindQueue.mockResolvedValue(
      queue([cand({ canonical_candidate_id: "Cm1", label_index: null,
                    verdict: "hit", unique_error_id: "a.jpg/M1" })]),
    );
    show();
    await screen.findByText("a.jpg");

    await click("오류 아니었다");

    const rows = putAdjudications.mock.calls.at(-1)![3];
    expect(rows[0]).toMatchObject({ verdict: "miss", unique_error_id: null });
  });
});

describe("조회와 판정이 겹칠 때", () => {
  test("응답 전에는 판정할 것이 없다", async () => {
    // 재검수 화면의 R1(늦은 응답이 신규 판정을 덮음)이 여기서는 구조적으로
    // 생기지 않는다. **그 이유를 검사로 고정한다** — 나중에 로딩 중에도
    // 목록을 그리도록 바꾸면 이 검사가 먼저 깨진다.
    let release!: (value: unknown) => void;
    getBlindQueue.mockReturnValue(new Promise((r) => (release = r)));
    show();

    expect(screen.queryByRole("button", { name: "오류였다" })).toBeNull();

    await act(async () => {
      release(queue([cand({ verdict: "hold" })]));
    });
    await screen.findByText("a.jpg");

    // 서버가 준 판정이 화면에 살아 있다.
    const pressed = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-pressed") === "true")
      .map((b) => b.textContent);
    expect(pressed).toEqual(["모르겠다"]);
  });

  test("다른 평가로 바꾸면 옛 후보를 먼저 치운다", async () => {
    // 남겨 두면 지난 평가의 후보를 새 묶음 해시로 저장하게 된다.
    getBlindQueue.mockResolvedValue(queue([cand()]));
    const { rerender } = show();
    await screen.findByText("a.jpg");

    let release!: (value: unknown) => void;
    getBlindQueue.mockReturnValue(new Promise((r) => (release = r)));
    await act(async () => {
      rerender(<BlindAdjudication datasetId={DS} evaluationId="e2" />);
    });

    expect(screen.queryByText("a.jpg")).toBeNull();
    expect(screen.queryByRole("button", { name: "오류였다" })).toBeNull();

    await act(async () => {
      release(queue([cand({ image: "b.jpg" })], { candidate_set_hash: "h2" }));
    });
    await screen.findByText("b.jpg");
  });

  test("목록을 못 불러오면 말한다", async () => {
    getBlindQueue.mockRejectedValue(new Error("끊김"));
    show();
    await screen.findByText(/불러오지 못했습니다/);
  });
});

describe("파일과 묶음이 어긋날 때", () => {
  test("판정 파일이 깨졌으면 빈 판정으로 시작하지 않고 알린다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()], { damaged: true }));
    show();
    await screen.findByText(/읽지 못했습니다/);
  });

  test("후보 목록이 바뀌었으면 재시도로 덮지 않고 알린다", async () => {
    getBlindQueue.mockResolvedValue(queue([cand()]));
    putAdjudications.mockRejectedValue(
      Object.assign(new Error("conflict"), { response: { status: 409 } }),
    );
    show();
    await screen.findByText("a.jpg");

    await click("오류였다");
    await screen.findByText(/후보 목록이 그 사이에 바뀌었습니다/);
  });
});

describe("진행 상황", () => {
  test("보류도 판정으로 센다", async () => {
    getBlindQueue.mockResolvedValue(
      queue([cand({ canonical_candidate_id: "A" }),
             cand({ canonical_candidate_id: "B" })]),
    );
    show();
    await screen.findByText("a.jpg");

    await click("모르겠다");
    await screen.findByText("1 / 2 판정 (남은 1)");
  });
});
