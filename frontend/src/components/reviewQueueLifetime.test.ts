/**
 * R5 — 판정의 수명 (docs/25).
 *
 * 판정은 데이터셋 단위로 묶이고 키는 `이미지#라벨번호#의심유형`이다. 같은
 * 데이터셋을 **다른 자로 다시 진단**하면 후보 목록이 달라지는데, 그때 옛 판정이
 * 어떻게 되는지가 이 절의 질문이다.
 *
 * **판정은 라벨에 대한 사실이다** — "이 박스가 틀렸는가"는 어느 모델로 봤든
 * 답이 같다. 그래서 라벨을 가리키는 후보는 계승이 맞다.
 *
 * 문제는 **누락 후보**다. 가리킬 라벨이 없어 키에 예측 좌표가 들어가는데
 * (docs/24 B1), 자가 바뀌면 예측이 달라져 좌표도 달라진다.
 */
import { describe, expect, test } from "vitest";

import { carryOverVerdicts, keyOf, orphanMessage, orphanReport, sameCandidate } from "./reviewQueueLogic";
import type { ReviewQueueItem } from "../types";

function item(over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    rank: 1, image: "a.png", label_index: 0, suspicion: "width",
    label: "가로", severity: 0.5, detail: "", box: [10, 20, 110, 220], ...over,
  };
}

describe("R5 재진단에서 무엇이 계승되는가", () => {
  test("라벨을 가리키는 후보는 자가 바뀌어도 같은 후보다", () => {
    // 심각도·근거·순위는 자마다 다르지만 가리키는 라벨은 같다.
    const before = item({ severity: 0.5, detail: "예측보다 28% 작음", rank: 3 });
    const after = item({ severity: 0.9, detail: "예측보다 41% 작음", rank: 1 });
    expect(keyOf(before)).toBe(keyOf(after));
  });

  test("누락 후보는 예측이 조금만 달라도 다른 키가 된다", () => {
    const before = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    const after = item({ label_index: null, suspicion: "missing", box: [11, 20, 60, 70] });
    expect(keyOf(before)).not.toBe(keyOf(after));
  });

  test("누락 후보가 같은 자리를 가리키면 같은 것으로 본다", () => {
    // 좌표가 조금 흔들려도 사람 눈에는 같은 박스다. 겹침으로 판단한다.
    const before = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    const after = item({ label_index: null, suspicion: "missing", box: [12, 22, 62, 72] });
    expect(sameCandidate(before, after)).toBe(true);
  });

  test("멀리 떨어진 누락 후보는 다른 것이다", () => {
    const a = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    const b = item({ label_index: null, suspicion: "missing", box: [300, 20, 350, 70] });
    expect(sameCandidate(a, b)).toBe(false);
  });

  test("유형이 다르면 겹쳐도 다른 후보다", () => {
    const a = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    const b = item({ label_index: null, suspicion: "duplicate", box: [10, 20, 60, 70] });
    expect(sameCandidate(a, b)).toBe(false);
  });

  test("이미지가 다르면 다른 후보다", () => {
    const a = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    const b = item({ image: "b.png", label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    expect(sameCandidate(a, b)).toBe(false);
  });
});

describe("carryOverVerdicts — 다시 진단한 뒤 판정을 옮긴다 (docs/25 R5)", () => {
  const labelled = item({ label_index: 0, suspicion: "width" });
  const missBefore = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
  const missAfter = item({ label_index: null, suspicion: "missing", box: [12, 22, 62, 72] });

  test("자리가 그대로면 그대로 둔다", () => {
    const r = carryOverVerdicts({ [keyOf(labelled)]: "hit" }, [labelled], [labelled]);
    expect(r.verdicts[keyOf(labelled)]).toBe("hit");
    expect(r.moved).toBe(0);
    expect(r.dropped).toBe(0);
  });

  test("누락 후보의 좌표가 흔들리면 옮긴다", () => {
    const r = carryOverVerdicts({ [keyOf(missBefore)]: "hit" }, [missBefore], [missAfter]);
    expect(r.verdicts[keyOf(missAfter)]).toBe("hit");
    expect(r.verdicts[keyOf(missBefore)]).toBeUndefined();
    expect(r.moved).toBe(1);
  });

  test("가리킬 후보가 없어졌으면 버리고 센다", () => {
    // 조용히 사라지면 검수자는 잃은 줄도 모른다.
    const r = carryOverVerdicts({ [keyOf(missBefore)]: "hit" }, [missBefore], [labelled]);
    expect(Object.keys(r.verdicts)).toHaveLength(0);
    expect(r.dropped).toBe(1);
  });

  test("한 후보에 둘이 붙지 않는다", () => {
    // 겹치는 옛 후보가 둘이면 하나만 옮겨야 한다.
    const other = item({ label_index: null, suspicion: "missing", box: [11, 21, 61, 71] });
    const r = carryOverVerdicts(
      { [keyOf(missBefore)]: "hit", [keyOf(other)]: "miss" },
      [missBefore, other], [missAfter]);
    expect(Object.keys(r.verdicts)).toHaveLength(1);
    expect(r.moved + r.dropped).toBe(2);
  });

  test("옛 후보 목록을 모르면 옮기지 못하고 버린다", () => {
    // 예전 진단 결과를 안 갖고 있을 수 있다. 그때는 계승을 지어내지 않는다.
    const r = carryOverVerdicts({ [keyOf(missBefore)]: "hit" }, [], [missAfter]);
    expect(r.dropped).toBe(1);
  });
});

describe("orphanReport — 화면에서 사라진 판정을 센다 (docs/25 R5)", () => {
  const labelled = item({ label_index: 0, suspicion: "width" });
  const missBefore = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
  const missAfter = item({ label_index: null, suspicion: "missing", box: [12, 22, 62, 72] });

  test("자리가 그대로면 아무것도 안 센다", () => {
    expect(orphanReport({ [keyOf(labelled)]: "hit" }, [labelled]))
      .toEqual({ orphaned: 0, movable: 0 });
  });

  test("옛 목록 없이도 키만 보고 짝을 찾는다", () => {
    // 누락 후보의 좌표는 키 안에 들어 있다.
    expect(orphanReport({ [keyOf(missBefore)]: "hit" }, [missAfter]))
      .toEqual({ orphaned: 1, movable: 1 });
  });

  test("가리킬 후보가 없으면 옮길 수 없다고 센다", () => {
    expect(orphanReport({ [keyOf(missBefore)]: "hit" }, [labelled]))
      .toEqual({ orphaned: 1, movable: 0 });
  });

  test("이미 판정된 후보로는 옮기지 않는다", () => {
    const v = { [keyOf(missBefore)]: "hit" as const, [keyOf(missAfter)]: "miss" as const };
    expect(orphanReport(v, [missAfter])).toEqual({ orphaned: 1, movable: 0 });
  });

  test("한 후보에 둘을 겹쳐 세지 않는다", () => {
    const other = item({ label_index: null, suspicion: "missing", box: [11, 21, 61, 71] });
    const v = { [keyOf(missBefore)]: "hit" as const, [keyOf(other)]: "miss" as const };
    expect(orphanReport(v, [missAfter])).toEqual({ orphaned: 2, movable: 1 });
  });

  test("말은 하되 지워지지 않았다고 알린다", () => {
    const m = orphanMessage(3, 2);
    expect(m).toContain("3건");
    expect(m).toContain("지워지지 않았고");
    expect(m).toContain("2건");
  });

  test("셀 것이 없으면 아무 말도 안 한다", () => {
    expect(orphanMessage(0, 0)).toBe("");
  });
});
