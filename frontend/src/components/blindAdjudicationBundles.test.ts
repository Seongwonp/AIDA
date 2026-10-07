/**
 * 묶음 나누기의 순수 규칙 (사전 등록 D5·D6, 개정 5).
 *
 * 목록은 서버가 묶음 순서로 준다. 화면은 그 목록을 묶음 구간으로 읽고, 자동 이동·재개·"다음 미판정"을
 * 묶음 안에 가둔다. 묶음이 없으면 예전 규칙 그대로다.
 */
import { describe, expect, test } from "vitest";

import {
  advanceTarget,
  bundleHeader,
  bundleLabel,
  bundleSpans,
  firstIncompleteSpan,
  nextUnjudgedInSpan,
  resumeIndex,
  spanAt,
  type BlindBundle,
  type BlindCandidate,
  type Judgements,
} from "./blindAdjudicationLogic";

const c = (id: string, bundle: number | undefined, missing = false): BlindCandidate => ({
  canonical_candidate_id: id,
  image: `${id}.jpg`,
  label_index: missing ? null : 0,
  box: [0, 0, 1, 1],
  verdict: null,
  unique_error_id: null,
  ...(bundle === undefined ? {} : { bundle }),
});

const LIST = [c("A", 0), c("B", 0), c("C", 1), c("D", 1), c("M", 2, true), c("N", 2, true)];
const BUNDLES: BlindBundle[] = [
  { index: 0, layer: "labelled_candidates", layer_bundle: 1, layer_bundles: 2, size: 2 },
  { index: 1, layer: "labelled_candidates", layer_bundle: 2, layer_bundles: 2, size: 2 },
  { index: 2, layer: "missing_candidates", layer_bundle: 1, layer_bundles: 1, size: 2 },
];
const judged = (...ids: string[]): Judgements =>
  Object.fromEntries(ids.map((id) => [id, { verdict: "miss" as const }]));

describe("묶음 구간", () => {
  test("묶음 표가 없으면 null — 옛 묶음은 한 목록", () => {
    expect(bundleSpans(LIST, undefined)).toBeNull();
    expect(bundleSpans(LIST, [])).toBeNull();
  });

  test("크기를 이어 붙여 구간을 만든다", () => {
    const spans = bundleSpans(LIST, BUNDLES)!;
    expect(spans.map((s) => [s.start, s.end])).toEqual([[0, 2], [2, 4], [4, 6]]);
    expect(spanAt(spans, 3)?.index).toBe(1);
    expect(spanAt(spans, null)).toBeNull();
  });

  test("목록과 어긋나면 던진다 — 크기 합·후보의 묶음 자리·층", () => {
    expect(() => bundleSpans(LIST.slice(1), BUNDLES)).toThrow();
    expect(() => bundleSpans([c("A", 1), ...LIST.slice(1)], BUNDLES)).toThrow();
    expect(() => bundleSpans([...LIST.slice(0, 4), c("M", 2), c("N", 2, true)], BUNDLES)).toThrow();
  });

  test("머리글 — 기존 라벨 묶음 2/2 · 2/2, 누락 묶음은 하나라 번호 없음", () => {
    const spans = bundleSpans(LIST, BUNDLES)!;
    expect(bundleHeader(spans[1], 3)).toBe("기존 라벨 묶음 2/2 · 2/2");
    expect(bundleHeader(spans[2], 4)).toBe("누락 묶음 · 1/2");
    expect(bundleLabel({ ...BUNDLES[0], layer_bundle: 2, layer_bundles: 4 })).toBe("기존 라벨 묶음 2/4");
  });
});

describe("묶음 안에 갇힌 이동", () => {
  const spans = bundleSpans(LIST, BUNDLES)!;

  test("다음 미판정은 묶음을 넘지 않고, 뒤에 없으면 묶음 앞쪽에서 찾는다", () => {
    // 묶음 2(C,D)가 다 찼으면 뒤 묶음(M,N)이 미판정이어도 null.
    expect(nextUnjudgedInSpan(LIST, judged("C", "D"), 2, spans[1])).toBeNull();
    // 자기 자신도 미판정이면 감싸 돌아 자기 자리(예전 "다음 미판정"과 같은 규칙).
    expect(nextUnjudgedInSpan(LIST, judged("D"), 2, spans[1])).toBe(2);
    expect(nextUnjudgedInSpan(LIST, judged("C", "D"), 1, spans[0])).toBe(0);
    expect(nextUnjudgedInSpan(LIST, judged("C"), 3, spans[1])).toBe(3);
  });

  test("자동 이동 — 묶음 안 → 묶음 완료 → 전부 끝나면 완료", () => {
    expect(advanceTarget(LIST, judged("A"), 0, spans)).toEqual({ kind: "candidate", index: 1 });
    expect(advanceTarget(LIST, judged("A", "B"), 1, spans)).toEqual({ kind: "bundle_complete", bundle: 0 });
    expect(advanceTarget(LIST, judged("A", "B", "C", "D", "M", "N"), 5, spans)).toEqual({ kind: "done" });
  });

  test("묶음이 없으면 예전 규칙 — 목록 끝에서 앞으로 감싸 돈다", () => {
    expect(advanceTarget(LIST, judged("B", "C", "D", "M", "N"), 5, null)).toEqual({ kind: "candidate", index: 0 });
    expect(advanceTarget(LIST, judged("A", "B", "C", "D", "M", "N"), 5, null)).toEqual({ kind: "done" });
  });

  test("재개 — 미판정이 남은 가장 앞 묶음의 첫 미판정", () => {
    expect(resumeIndex(LIST, judged(), spans)).toBe(0);
    expect(resumeIndex(LIST, judged("A"), spans)).toBe(1);
    // 앞 묶음이 끝났으면 다음 묶음의 첫 미판정(완료 화면을 다시 띄우지 않는다).
    expect(resumeIndex(LIST, judged("A", "B", "C"), spans)).toBe(3);
    expect(resumeIndex(LIST, judged("A", "B", "C", "D"), spans)).toBe(4);
    // 뒤 묶음을 판정했어도 앞 묶음에 빈 자리가 있으면 거기부터.
    expect(resumeIndex(LIST, judged("B", "C", "D"), spans)).toBe(0);
    expect(resumeIndex(LIST, judged("A", "B", "C", "D", "M", "N"), spans)).toBeNull();
    expect(firstIncompleteSpan(LIST, judged("A", "B"), spans)?.index).toBe(1);
  });
});
