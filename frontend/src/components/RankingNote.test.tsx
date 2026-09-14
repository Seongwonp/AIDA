import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RankingNote } from "./RankingNote";
import type { RankingInfo } from "../types";

// 버전 이름은 문자열로 직접 적는다 — 상수를 쓰면 v1·v2가 뒤바뀌어도 통과한다.
const info = (version: string, legacy = false): RankingInfo => ({
  ranking_version: version,
  ranking_scope: version === "aida_v2_candidate_iou" ? "per_layer" : "mixed_queue",
  ranking_signal: {},
  dataset_boost_affects_order: version !== "aida_v2_candidate_iou",
  tie_break_rule: "",
  legacy,
});

afterEach(cleanup);

const NO_BOOST = /모두 위로 올리지 않습니다/;
const BOOST = /계통적이라고 본 유형의 후보를 모두 먼저/;

describe("RankingNote", () => {
  it("v2 결과는 데이터셋 유형이 후보를 통째로 올리지 않는다고 말하고, 낫다고 하지 않는다", () => {
    render(<RankingNote ranking={info("aida_v2_candidate_iou")} />);
    expect(screen.getByText(/v2 · 후보 단위 순서/)).toBeTruthy();
    expect(screen.getByText(NO_BOOST)).toBeTruthy();
    expect(screen.getByText(/낫다는 검증은 없습니다/)).toBeTruthy();
    expect(screen.queryByText(BOOST)).toBeNull();
  });

  it("v1 결과는 계통 유형을 먼저 올린다고 말한다", () => {
    render(<RankingNote ranking={info("aida_v1_systematic_boost")} />);
    expect(screen.getByText(/v1 · 기존 제품 순서/)).toBeTruthy();
    expect(screen.getByText(BOOST)).toBeTruthy();
    expect(screen.queryByText(NO_BOOST)).toBeNull();
    expect(screen.queryByText(/옛 결과/)).toBeNull();
  });

  it("버전 기록이 없으면 v1으로 읽었다고 밝힌다", () => {
    render(<RankingNote ranking={null} />);
    expect(screen.getByText(/옛 결과라 v1으로 읽었습니다/)).toBeTruthy();
    expect(screen.getByText(BOOST)).toBeTruthy();
  });

  it("데이터셋 진단과 재검수 순서가 다른 질문이라고 말한다", () => {
    render(<RankingNote ranking={info("aida_v2_candidate_iou")} />);
    expect(screen.getByText(/데이터셋 진단은 데이터셋 전체에서/)).toBeTruthy();
    expect(screen.getByText(/개별 후보를 어떤 순서로 볼지/)).toBeTruthy();
  });
});
