import { beforeEach, describe, expect, test, vi } from "vitest";

// localStorage 하나 때문에 jsdom을 통째로 들이지 않는다. 쓰는 것은 세 개뿐이라
// 여기서 흉내 내는 편이 의존성 하나를 아낀다.
const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
  clear: () => store.clear(),
});

import type { ReviewQueueItem } from "../types";
import {
  clearVerdicts,
  keyOf,
  loadVerdicts,
  nextCursor,
  STORE,
  toCsv,
} from "./reviewQueueLogic";

/**
 * 프론트에 검사가 하나도 없었다. 타입체크와 린트는 "말이 되는가"만 보지
 * "맞는가"는 안 본다. 여기 모은 것들은 눈으로 봐서는 틀린 줄 모르는 종류다.
 */

function item(over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    rank: 1,
    image: "000001.png",
    label_index: 0,
    suspicion: "width",
    label: "가로 길이 어긋남",
    severity: 0.5,
    detail: "예측보다 28% 작습니다",
    box: [10, 20, 110, 220],
    ...over,
  };
}

describe("nextCursor — 판정한 뒤 어디로 가는가", () => {
  test("보통은 다음 줄로 내려간다", () => {
    expect(nextCursor(2, 10, false)).toBe(3);
  });

  test('"안 본 것만"이면 제자리에 머문다', () => {
    // 판정한 줄이 사라지고 그 자리에 다음 항목이 올라온다. +1 하면 건너뛴다.
    expect(nextCursor(2, 10, true)).toBe(2);
  });

  test("마지막 줄을 판정해도 범위를 벗어나지 않는다", () => {
    expect(nextCursor(9, 10, false)).toBe(9);
    expect(nextCursor(9, 10, true)).toBe(8);
  });

  test("한 건뿐일 때 음수로 내려가지 않는다", () => {
    expect(nextCursor(0, 1, true)).toBe(0);
    expect(nextCursor(0, 1, false)).toBe(0);
  });
});

describe("keyOf — 판정을 어디에 매다는가", () => {
  test("같은 이미지의 다른 박스는 다른 키다", () => {
    expect(keyOf(item({ label_index: 0 }))).not.toBe(keyOf(item({ label_index: 1 })));
  });

  test("같은 박스의 다른 의심 유형도 다른 키다", () => {
    expect(keyOf(item({ suspicion: "width" })))
      .not.toBe(keyOf(item({ suspicion: "height" })));
  });

  test("라벨이 없는 누락 의심도 키가 생긴다", () => {
    expect(keyOf(item({ label_index: null, suspicion: "missing" })))
      .toBe("000001.png#none#missing");
  });

  test("순위가 바뀌어도 키는 그대로다", () => {
    // 다시 진단해서 순서가 달라져도 어제 판정이 붙어 있어야 한다
    expect(keyOf(item({ rank: 1 }))).toBe(keyOf(item({ rank: 7 })));
  });
});

describe("loadVerdicts — 검수 진행이 업데이트로 날아가면 안 된다", () => {
  beforeEach(() => localStorage.clear());

  test("아무것도 없으면 빈 것", () => {
    expect(loadVerdicts("ds1")).toEqual({});
  });

  test("저장해 둔 판정을 그대로 읽는다", () => {
    localStorage.setItem(STORE("ds1"), JSON.stringify({ "a#0#width": "miss" }));
    expect(loadVerdicts("ds1")).toEqual({ "a#0#width": "miss" });
  });

  test("이전 버전의 \"봤다\" 목록을 살려 온다", () => {
    // 예전에는 본 것만 배열로 저장했다. 검수하던 사람의 진행이 날아가면 안 된다.
    localStorage.setItem("aida-reviewed-ds1", JSON.stringify(["a#0#width", "b#1#height"]));
    expect(loadVerdicts("ds1")).toEqual({ "a#0#width": "hit", "b#1#height": "hit" });
  });

  test("새 형식이 있으면 옛 형식은 무시한다", () => {
    localStorage.setItem(STORE("ds1"), JSON.stringify({ "a#0#width": "miss" }));
    localStorage.setItem("aida-reviewed-ds1", JSON.stringify(["z#9#missing"]));
    expect(loadVerdicts("ds1")).toEqual({ "a#0#width": "miss" });
  });

  test("데이터셋마다 따로 남는다", () => {
    localStorage.setItem(STORE("ds1"), JSON.stringify({ "a#0#width": "hit" }));
    expect(loadVerdicts("ds2")).toEqual({});
  });

  test("깨진 값이 있어도 화면이 죽지 않는다", () => {
    localStorage.setItem(STORE("ds1"), "{나쁜 JSON");
    expect(loadVerdicts("ds1")).toEqual({});
  });
});

describe("toCsv — 받는 쪽은 엑셀과 라벨링 도구다", () => {
  test("머리글과 줄 수", () => {
    const csv = toCsv([item(), item({ rank: 2 })], {});
    const lines = csv.split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toContain("x1,y1,x2,y2");
  });

  test("엑셀이 한글을 읽으려면 BOM이 있어야 한다", () => {
    expect(toCsv([item()], {}).charCodeAt(0)).toBe(0xfeff);
  });

  test("좌표를 소수 한 자리로 낸다", () => {
    expect(toCsv([item({ box: [10.44, 20.55, 110, 220] })], {}))
      .toContain("10.4,20.6,110.0,220.0");
  });

  test("좌표가 없으면 빈 칸 네 개", () => {
    // 누락 의심은 가리킬 라벨이 없다. 예전 진단 결과에도 좌표가 없다.
    const row = toCsv([item({ box: null })], {}).split("\n")[1];
    expect(row).toContain(",,,,,");
  });

  test("쉼표가 든 근거를 한 칸으로 지킨다", () => {
    const row = toCsv([item({ detail: "예측보다 28% 작고, 중심도 밀렸습니다" })], {})
      .split("\n")[1];
    expect(row).toContain('"예측보다 28% 작고, 중심도 밀렸습니다"');
    // 감싸지 않으면 칸이 하나 더 생겨 뒤가 전부 밀린다
    expect(row.split(",").length).toBe(12);
  });

  test("따옴표는 겹따옴표로 escape 한다", () => {
    expect(toCsv([item({ image: 'a".png' })], {}).split("\n")[1])
      .toContain('"a"".png"');
  });

  test("판정한 것만 판정 칸이 찬다", () => {
    const a = item();
    const csv = toCsv([a, item({ image: "b.png" })], { [keyOf(a)]: "miss" });
    const [, first, second] = csv.split("\n");
    expect(first.endsWith("오류 아님")).toBe(true);
    expect(second.endsWith(",")).toBe(true);
  });
});

describe("clearVerdicts — 데이터셋을 지우면 판정도 따라간다", () => {
  beforeEach(() => localStorage.clear());

  test("새 형식과 옛 형식을 둘 다 지운다", () => {
    // 하나만 지우면 다음에 열 때 옛 형식에서 되살아난다
    localStorage.setItem(STORE("ds1"), JSON.stringify({ "a#0#width": "hit" }));
    localStorage.setItem("aida-reviewed-ds1", JSON.stringify(["b#1#height"]));
    clearVerdicts("ds1");
    expect(loadVerdicts("ds1")).toEqual({});
  });

  test("다른 데이터셋은 건드리지 않는다", () => {
    localStorage.setItem(STORE("ds1"), JSON.stringify({ "a#0#width": "hit" }));
    localStorage.setItem(STORE("ds2"), JSON.stringify({ "b#1#height": "miss" }));
    clearVerdicts("ds1");
    expect(loadVerdicts("ds2")).toEqual({ "b#1#height": "miss" });
  });
});
