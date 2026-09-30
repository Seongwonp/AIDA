import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Guide } from "./Guide";
import { JudgingGuideline } from "./JudgingGuideline";
import { CANDIDATE_COLOR, CONTEXT_COLOR, MISSING_COLOR } from "./AdjudicationView";

describe("Guide", () => {
  it("분석 단계와 업로드 형식을 보여 준다", () => {
    render(<Guide />);
    expect(screen.getByRole("heading", { name: "어떻게 분석하나요?" })).toBeTruthy();
    for (const step of ["데이터 준비", "기준 모델(자) 고르기 — 가장 중요", "순서 버전 고르기", "결과 읽기", "재검수하기"]) {
      expect(screen.getByRole("heading", { name: step })).toBeTruthy();
    }
    expect(screen.getByText(/200MB 이하/)).toBeTruthy();
  });
});

describe("JudgingGuideline", () => {
  it("세 판정과 화면 색을 설명한다", () => {
    render(<JudgingGuideline />);
    expect(screen.getAllByText("오류였다").length).toBeGreaterThan(0);
    expect(screen.getAllByText("오류 아니었다").length).toBeGreaterThan(0);
    expect(screen.getAllByText("모르겠다").length).toBeGreaterThan(0);
    expect(screen.getAllByText("주황 점선").length).toBeGreaterThan(0);
  });

  it("지침의 색 이름이 실제 판정 화면의 색과 맞는다", () => {
    // 지침 문서는 누락을 "빨강 점선"이라 적었지만 화면은 주황이다. 화면 색이 바뀌면 이 검사가 깨진다.
    expect(CANDIDATE_COLOR).toBe("#e11d48");
    expect(MISSING_COLOR).toBe("#d97706");
    expect(CONTEXT_COLOR).toBe("#2563eb");
  });
});
