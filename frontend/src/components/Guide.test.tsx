import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Guide } from "./Guide";
import { JudgingGuideline } from "./JudgingGuideline";
import { CANDIDATE_COLOR, CONTEXT_COLOR, MISSING_COLOR } from "./AdjudicationView";
import { REFLECTION_HOLD, REFLECTION_KO, REFLECTION_SOURCE } from "./reflectionRule";

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
    expect(screen.getAllByText("오류 있음").length).toBeGreaterThan(0);
    expect(screen.getAllByText("오류 없음").length).toBeGreaterThan(0);
    expect(screen.getAllByText("판단 보류").length).toBeGreaterThan(0);
    expect(screen.getAllByText("주황 점선").length).toBeGreaterThan(0);
  });

  it("지침의 색 이름이 실제 판정 화면의 색과 맞는다", () => {
    // 지침 문서는 누락을 "빨강 점선"이라 적었지만 화면은 주황이다. 화면 색이 바뀌면 이 검사가 깨진다.
    expect(CANDIDATE_COLOR).toBe("#e11d48");
    expect(MISSING_COLOR).toBe("#d97706");
    expect(CONTEXT_COLOR).toBe("#2563eb");
  });

  it("유리 반사는 공식 원문·번역·보류 원칙만 보이고 원문에 없는 해석은 없다", () => {
    const { container } = render(<JudgingGuideline />);
    const text = container.textContent ?? "";
    expect(REFLECTION_SOURCE).toBe(
      "If an object is reflected clearly in a glass window, then the reflection should be annotated.");
    expect(REFLECTION_KO).toBe("객체가 유리창에 선명하게 반사되었다면 그 반사상도 라벨 대상입니다.");
    expect(REFLECTION_HOLD).toBe("이 원문만으로 판단하기 어렵거나 선명한지 애매하면 판단 보류를 선택하세요.");
    for (const s of [REFLECTION_SOURCE, REFLECTION_KO, REFLECTION_HOLD]) expect(text).toContain(s);
    // 지운 해석이 다시 들어오면 깨진다.
    for (const banned of ["물웅덩이", "차체", "비친 상 위", "흐릿하거나"]) expect(text).not.toContain(banned);
  });
});
