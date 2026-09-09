/**
 * 가림 판정의 규칙 (docs/evaluation-adjudication-design.md).
 *
 * 여기서 고정하는 것은 **화면이 서버에 무엇을 보내는가**다. 서버도 같은 것을
 * 검사하지만(backend/tests/test_evaluation_adjudication.py), 화면이 먼저
 * 막아야 판정자가 저장 실패를 겪지 않는다.
 */
import { describe, expect, test, vi } from "vitest";

import {
  blockedIds,
  firstUnjudgedIndex,
  nextUnjudgedIndex,
  unjudgedCount,
  makeAdjudicationSender,
  missingName,
  missingObjects,
  nextMissingObject,
  progress,
  toJudgements,
  toRequest,
  type BlindCandidate,
} from "./blindAdjudicationLogic";

function cand(over: Partial<BlindCandidate> = {}): BlindCandidate {
  return {
    canonical_candidate_id: "Labc",
    image: "a.jpg",
    label_index: 0,
    box: [1, 2, 3, 4],
    verdict: null,
    unique_error_id: null,
    ...over,
  };
}

describe("서버가 준 것을 화면 상태로", () => {
  test("판정 없음은 null이고 hold가 아니다", () => {
    const got = toJudgements([cand()]);
    expect(got.Labc.verdict).toBeNull();
  });

  test("누락 객체 이름에서 이미지를 뗀다", () => {
    const got = toJudgements([
      cand({ canonical_candidate_id: "Cxyz", label_index: null, verdict: "hit", unique_error_id: "a.jpg/M2" }),
    ]);
    expect(got.Cxyz.missingObject).toBe("M2");
  });

  test("다른 이미지의 이름은 안 받는다", () => {
    // 받아 버리면 두 이미지의 오류가 한 오류로 세어진다.
    expect(missingName("a.jpg", "b.jpg/M1")).toBeNull();
    expect(missingName("a.jpg", "a.jpg/M1")).toBe("M1");
    expect(missingName("a.jpg", "M1")).toBe("M1");
    expect(missingName("a.jpg", null)).toBeNull();
  });
});

describe("누락 객체 이름 붙이기", () => {
  const cands = [
    cand({ canonical_candidate_id: "C1", image: "a.jpg", label_index: null }),
    cand({ canonical_candidate_id: "C2", image: "a.jpg", label_index: null }),
    cand({ canonical_candidate_id: "C3", image: "b.jpg", label_index: null }),
  ];

  test("이미 만든 것만 이어 붙일 수 있게 보여준다", () => {
    const j = { C1: { verdict: "hit" as const, missingObject: "M1" } };
    expect(missingObjects(cands, j, "a.jpg")).toEqual(["M1"]);
    // 다른 이미지의 것은 안 나온다.
    expect(missingObjects(cands, j, "b.jpg")).toEqual([]);
  });

  test("새 이름은 그 이미지 안에서 다음 번호다", () => {
    expect(nextMissingObject(cands, {}, "a.jpg")).toBe("M1");
    const j = { C1: { verdict: "hit" as const, missingObject: "M1" } };
    expect(nextMissingObject(cands, j, "a.jpg")).toBe("M2");
    // 이미지가 다르면 다시 M1부터다.
    expect(nextMissingObject(cands, j, "b.jpg")).toBe("M1");
  });

  test("번호는 이미지마다 따로 매긴다", () => {
    const j = {
      C1: { verdict: "hit" as const, missingObject: "M1" },
      C3: { verdict: "hit" as const, missingObject: "M1" },
    };
    // 이름이 같아도 이미지가 다르면 서버에서 다른 오류가 된다.
    expect(missingObjects(cands, j, "a.jpg")).toEqual(["M1"]);
    expect(missingObjects(cands, j, "b.jpg")).toEqual(["M1"]);
  });
});

describe("보낼 수 없는 판정", () => {
  test("누락 hit인데 객체를 안 정하면 막는다", () => {
    const cands = [cand({ canonical_candidate_id: "C1", label_index: null })];
    expect(blockedIds(cands, { C1: { verdict: "hit" } })).toEqual(["C1"]);
    expect(blockedIds(cands, { C1: { verdict: "hit", missingObject: "M1" } })).toEqual([]);
  });

  test("기존 라벨 hit은 안 막는다 — 서버가 이름을 정한다", () => {
    expect(blockedIds([cand()], { Labc: { verdict: "hit" } })).toEqual([]);
  });

  test("miss와 hold는 객체가 없어도 된다", () => {
    const cands = [cand({ canonical_candidate_id: "C1", label_index: null })];
    expect(blockedIds(cands, { C1: { verdict: "miss" } })).toEqual([]);
    expect(blockedIds(cands, { C1: { verdict: "hold" } })).toEqual([]);
  });
});

describe("서버에 보낼 모양", () => {
  test("기존 라벨에는 오류 이름을 안 붙인다", () => {
    // 서버가 정한다. 화면이 붙이면 둘 중 무엇이 맞는지 모르게 된다.
    const rows = toRequest([cand()], { Labc: { verdict: "hit" } });
    expect(rows[0].unique_error_id).toBeNull();
  });

  test("누락 hit에는 화면이 정한 이름을 붙인다", () => {
    const cands = [cand({ canonical_candidate_id: "C1", label_index: null })];
    const rows = toRequest(cands, { C1: { verdict: "hit", missingObject: "M2" } });
    expect(rows[0].unique_error_id).toBe("M2");
  });

  test("hit이 아니면 이름을 떼고 보낸다", () => {
    const cands = [cand({ canonical_candidate_id: "C1", label_index: null })];
    const rows = toRequest(cands, { C1: { verdict: "miss", missingObject: "M2" } });
    expect(rows[0].unique_error_id).toBeNull();
  });

  test("판정 취소도 보낸다 — 안 보내면 서버의 옛 판정이 남는다", () => {
    const rows = toRequest([cand()], { Labc: { verdict: null } });
    expect(rows).toHaveLength(1);
    expect(rows[0].verdict).toBeNull();
  });
});

describe("진행 상황", () => {
  test("보류도 판정으로 센다 — 사람이 시간을 썼다", () => {
    const cands = [cand({ canonical_candidate_id: "A" }), cand({ canonical_candidate_id: "B" })];
    const got = progress(cands, { A: { verdict: "hold" } });
    expect(got).toMatchObject({ total: 2, judged: 1, left: 1 });
  });

  test("정밀도를 계산하지 않는다", () => {
    // 화면에 정밀도가 뜨면 판정자가 그것을 보고 다음 판정을 조절한다.
    const got = progress([cand()], { Labc: { verdict: "hit" } });
    expect(Object.keys(got)).toEqual(["total", "judged", "blocked", "left"]);
  });
});

describe("저장 직렬화", () => {
  test("한 번에 하나씩 보낸다", async () => {
    const order: string[] = [];
    let release: (() => void) | null = null;
    const send = vi.fn(async (rows: string) => {
      order.push(`start:${rows}`);
      if (rows === "first") await new Promise<void>((r) => (release = r));
      order.push(`end:${rows}`);
    });
    const sender = makeAdjudicationSender(send);

    const a = sender("first");
    const b = sender("second");
    expect(order).toEqual(["start:first"]);   // 두 번째는 아직 안 나갔다

    release!();
    await Promise.all([a, b]);
    expect(order).toEqual(["start:first", "end:first", "start:second", "end:second"]);
  });

  test("기다리는 동안 여러 번 바꾸면 마지막 것만 보낸다", async () => {
    let release: (() => void) | null = null;
    const send = vi.fn(async (rows: string) => {
      if (rows === "first") await new Promise<void>((r) => (release = r));
    });
    const sender = makeAdjudicationSender(send);

    const a = sender("first");
    const b = sender("second");
    const c = sender("third");
    release!();
    await Promise.all([a, b, c]);

    expect(send.mock.calls.map((call) => call[0])).toEqual(["first", "third"]);
  });

  test("실패를 삼키지 않고 알린다", async () => {
    const sender = makeAdjudicationSender(async () => {
      throw new Error("끊김");
    });
    await expect(sender("x")).resolves.toBe(false);
  });
});

describe("어디서부터 다시 시작하는가", () => {
  const cands = [
    cand({ canonical_candidate_id: "A" }),
    cand({ canonical_candidate_id: "B" }),
    cand({ canonical_candidate_id: "C" }),
  ];

  test("아직 판정 안 한 첫 후보를 찾는다", () => {
    // 두 번째 세션이 0번부터 시작하면 이미 판정한 후보를 넘기는 시간이
    // 그 후보들의 판정 시간에 다시 쌓인다.
    expect(firstUnjudgedIndex(cands, {})).toBe(0);
    expect(firstUnjudgedIndex(cands, { A: { verdict: "hit" } })).toBe(1);
    expect(firstUnjudgedIndex(cands, {
      A: { verdict: "hit" }, B: { verdict: "hold" },
    })).toBe(2);
  });

  test("보류도 판정이라 건너뛴다", () => {
    // 사람이 시간을 썼고 결과를 남겼다. 다시 열 이유가 없다.
    expect(firstUnjudgedIndex(cands, { A: { verdict: "hold" } })).toBe(1);
  });

  test("판정을 취소하면 다시 미판정이다", () => {
    expect(firstUnjudgedIndex(cands, { A: { verdict: null } })).toBe(0);
  });

  test("전부 판정했으면 자리가 없다", () => {
    // **0번을 다시 열면 안 된다.** 그 시간이 이미 판정한 후보에 쌓인다.
    const all = {
      A: { verdict: "hit" as const }, B: { verdict: "miss" as const },
      C: { verdict: "hold" as const },
    };
    expect(firstUnjudgedIndex(cands, all)).toBeNull();
    expect(unjudgedCount(cands, all)).toBe(0);
  });

  test("다음 미판정은 뒤에서 먼저 찾는다", () => {
    expect(nextUnjudgedIndex(cands, { A: { verdict: "hit" } }, 0)).toBe(1);
  });

  test("뒤에 없으면 앞으로 감싸 돈다", () => {
    // 보류로 미뤄 두고 넘어간 것이 앞쪽에 남아 있을 수 있다.
    const j = { B: { verdict: "hit" as const }, C: { verdict: "hit" as const } };
    expect(nextUnjudgedIndex(cands, j, 2)).toBe(0);
  });

  test("전부 판정했으면 다음도 없다", () => {
    const all = {
      A: { verdict: "hit" as const }, B: { verdict: "hit" as const },
      C: { verdict: "hit" as const },
    };
    expect(nextUnjudgedIndex(cands, all, 0)).toBeNull();
  });
});
