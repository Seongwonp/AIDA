/**
 * D8-3 재판정 화면 (사전 등록 개정 6).
 *
 * 보조 판정자(`primary_retest`)로 열면 목록·저장·작업 기록이 모두 그 판정자 이름으로 가야 한다 — 하나라도
 * 주 판정자로 가면 첫 판정 파일이나 본 판정 기록을 건드린다. 주 판정자로 열면 예전과 똑같이 판정자 인자를
 * `primary`로 보낸다(주소에 쿼리가 붙지 않는다 — `adjudicatorQuery`).
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
import { queueKey } from "./activityLog";
import { adjudicatorQuery, isAdjudicatorId, PRIMARY_ADJUDICATOR } from "../adjudicator";

const DS = "0123456789ab";
const EVAL = "qa1b";

function cand(id: string) {
  return { canonical_candidate_id: id, image: `${id}.jpg`, label_index: 0, box: [1, 2, 3, 4],
           verdict: null, unique_error_id: null };
}

beforeEach(() => {
  getBlindQueue.mockReset();
  getBlindQueue.mockResolvedValue({ evaluation_id: EVAL, dataset_id: DS, candidate_set_hash: "h1",
                                    candidates: [cand("A"), cand("B")], damaged: false });
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

describe("판정자 쿼리", () => {
  test("주 판정자는 쿼리가 없고 보조 판정자만 붙는다", () => {
    expect(adjudicatorQuery()).toBe("");
    expect(adjudicatorQuery(PRIMARY_ADJUDICATOR)).toBe("");
    expect(adjudicatorQuery("primary_retest")).toBe("?adjudicator=primary_retest");
  });

  test("형식은 서버와 같다 — 소문자·숫자·_·-, 20자 이내", () => {
    expect(isAdjudicatorId("primary_retest")).toBe(true);
    expect(isAdjudicatorId("Primary")).toBe(false);
    expect(isAdjudicatorId("a b")).toBe(false);
    expect(isAdjudicatorId("x".repeat(21))).toBe(false);
  });
});

describe("재판정 화면", () => {
  test("목록·저장·작업 기록이 모두 primary_retest로 간다", async () => {
    render(<BlindAdjudication datasetId={DS} evaluationId={EVAL} adjudicator="primary_retest" />);
    await waitFor(() => expect(getBlindQueue).toHaveBeenCalled());
    expect(getBlindQueue).toHaveBeenCalledWith(DS, EVAL, "primary_retest");
    await screen.findAllByRole("button", { name: "오류 없음" });
    await act(async () => screen.getAllByRole("button", { name: "오류 없음" })[0].click());
    await waitFor(() => expect(putAdjudications).toHaveBeenCalled());
    for (const call of putAdjudications.mock.calls) expect(call[4]).toBe("primary_retest");
    // 기록 전송은 주기·종료 때 일어난다 — 언마운트로 밀어낸다.
    cleanup();
    await waitFor(() => expect(postActivity).toHaveBeenCalled());
    for (const call of postActivity.mock.calls) expect(call[4]).toBe("primary_retest");
  });

  test("미전송 기록 보관 키도 판정자별이다 — 주 판정자 키는 예전 그대로", async () => {
    postActivity.mockRejectedValue(new Error("offline"));   // 못 보내면 저장소에 남는다
    render(<BlindAdjudication datasetId={DS} evaluationId={EVAL} adjudicator="primary_retest" />);
    await waitFor(() => expect(getBlindQueue).toHaveBeenCalled());
    cleanup();
    await waitFor(() => expect(postActivity).toHaveBeenCalled());
    await waitFor(() => expect(localStorage.getItem(`${queueKey(DS, EVAL)}.primary_retest`)).not.toBeNull());
    expect(localStorage.getItem(queueKey(DS, EVAL))).toBeNull();
  });

  test("판정자를 주지 않으면 주 판정자로 예전과 같이 부른다", async () => {
    render(<BlindAdjudication datasetId={DS} evaluationId={EVAL} />);
    await waitFor(() => expect(getBlindQueue).toHaveBeenCalledWith(DS, EVAL, PRIMARY_ADJUDICATOR));
  });
});
