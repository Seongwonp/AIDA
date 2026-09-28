/**
 * 외부 자로 잰 결과가 **어느 가중치로 잰 것인지** 화면에 남는가 (사전 등록 D1).
 */
import { afterEach, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { RulerCard } from "./RulerCard";
import type { LabelDiagnosisResult, RulerInfo } from "../types";

afterEach(cleanup);

const SHA = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";

const result = (extra: Partial<RulerInfo>) =>
  ({
    ruler: {
      profile: "",
      profile_label: "nuImages Car 자",
      classes: ["Car"],
      weights: "car_v1_e100",
      class_aware: false,
      seed_spread_pp: 1.23,
      unknown_class_ids: [],
      ...extra,
    },
    ruler_fit: null,
    robustness: [],
  }) as unknown as LabelDiagnosisResult;

test("외부 자면 ruler_id와 가중치 해시 앞 12자를 보여 준다", () => {
  render(<RulerCard result={result({ ruler_id: "nuimages_car_v1_e100", weights_sha256: SHA })} />);
  expect(screen.getByText("자 ID")).toBeTruthy();
  expect(screen.getByText(/nuimages_car_v1_e100/)).toBeTruthy();
  expect(screen.getByText(/abcdef012345…/)).toBeTruthy();
  // 해시 전체를 흘리지 않는다 — 앞 12자면 대조에 충분하다.
  expect(screen.queryByText(new RegExp(SHA))).toBeNull();
});

test("기본 기준 모델이면 자 ID 줄이 아예 없다", () => {
  render(<RulerCard result={result({})} />);
  expect(screen.queryByText("자 ID")).toBeNull();
});
