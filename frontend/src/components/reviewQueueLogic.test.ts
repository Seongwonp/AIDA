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
  loadSeen,
  saveStatusMessage,
  saveVerdicts,
  makeVerdictSender,
  type Verdicts,
  csvScopeNote,
  loadVerdicts,
  nextCursor,
  STORE,
  toCsv,
} from "./reviewQueueLogic";

/**
 * 프론트에 검사가 하나도 없었다. 타입체크와 린트는 "말이 되는가"만 보지
 * "맞는가"는 안 본다. 여기 모은 것들은 눈으로 봐서는 틀린 줄 모르는 종류다.
 */

/**
 * CSV 한 줄을 칸으로 나눈다 — 따옴표 안의 쉼표는 세지 않는다.
 *
 * 원래 `row.split(",")`로 칸 수를 셌는데, 그건 따옴표 안 쉼표도 쪼개므로
 * "칸이 몇 개인가"를 재는 게 아니었다. 재려는 것을 실제로 재려면 이만큼은
 * 필요하다.
 */
function parseCsvRow(row: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < row.length; i++) {
    const ch = row[i];
    if (quoted) {
      if (ch === '"') {
        if (row[i + 1] === '"') { cur += '"'; i++; }   // "" → 따옴표 한 개
        else quoted = false;
      } else cur += ch;
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      out.push(cur); cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

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
      .toBe("000001.png#none#missing#10,20,110,220");
  });

  // docs/24 B1. 누락 의심은 대응하는 라벨이 없어 label_index가 null이다.
  // 이미지 한 장에 누락 후보가 여럿이면 예전 키는 전부 같은 값이 됐고,
  // 하나를 판정하면 나머지도 같이 판정된 것으로 보였다.
  test("같은 이미지의 누락 후보 둘은 다른 키다", () => {
    const a = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    const b = item({ label_index: null, suspicion: "missing", box: [200, 30, 260, 90] });
    expect(keyOf(a)).not.toBe(keyOf(b));
  });

  test("판정이 이웃 후보로 번지지 않는다", () => {
    const a = item({ label_index: null, suspicion: "missing", box: [10, 20, 60, 70] });
    const b = item({ label_index: null, suspicion: "missing", box: [200, 30, 260, 90] });
    const verdicts = { [keyOf(a)]: "hit" as const };
    expect(verdicts[keyOf(b)]).toBeUndefined();
  });

  test("라벨이 있는 후보의 키는 예전 그대로다", () => {
    // 좌표를 붙이는 것은 라벨 인덱스가 없을 때뿐이다. 그래야 이미 저장된
    // 판정이 그대로 살아난다.
    expect(keyOf(item({ label_index: 3, suspicion: "width" })))
      .toBe("000001.png#3#width");
  });

  test("좌표가 없는 예전 진단 결과도 키가 생긴다", () => {
    // box는 나중에 추가된 필드라 예전 결과에는 없다(types.ts 주석).
    expect(keyOf(item({ label_index: null, suspicion: "missing", box: null })))
      .toBe("000001.png#none#missing#nobox");
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

  // docs/24 B1. 이전 형식은 "봤다"만 배열로 저장했다. 그것을 "오류 맞음"으로
  // 읽으면 **이 데이터셋의 정밀도가 100%로 보고된다** — 보기만 한 것이 전부
  // 맞은 것으로 세어지기 때문이다. 판정이 아니라 진행 표시로 살린다.
  test("이전 버전의 \"봤다\"는 판정으로 세지 않는다", () => {
    localStorage.setItem("aida-reviewed-ds1", JSON.stringify(["a#0#width", "b#1#height"]));
    expect(loadVerdicts("ds1")).toEqual({});
  });

  test("그래도 진행은 살아 있다", () => {
    localStorage.setItem("aida-reviewed-ds1", JSON.stringify(["a#0#width", "b#1#height"]));
    expect(loadSeen("ds1")).toEqual(new Set(["a#0#width", "b#1#height"]));
  });

  test("새 형식이 있으면 옛 형식은 무시한다", () => {
    localStorage.setItem(STORE("ds1"), JSON.stringify({ "a#0#width": "miss" }));
    localStorage.setItem("aida-reviewed-ds1", JSON.stringify(["z#9#missing"]));
    expect(loadVerdicts("ds1")).toEqual({ "a#0#width": "miss" });
  });

  test("판정한 것은 본 것이기도 하다", () => {
    // 화면의 "안 본 것만" 필터가 둘을 합쳐 봐야 한다.
    localStorage.setItem(STORE("ds1"), JSON.stringify({ "a#0#width": "miss" }));
    localStorage.setItem("aida-reviewed-ds1", JSON.stringify(["b#1#height"]));
    expect(loadSeen("ds1")).toEqual(new Set(["b#1#height"]));
    expect(Object.keys(loadVerdicts("ds1"))).toEqual(["a#0#width"]);
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
    const detail = "예측보다 28% 작고, 중심도 밀렸습니다";
    const csv = toCsv([item({ detail })], {});
    const [head, row] = csv.split("\n");
    // 감싸지 않으면 칸이 하나 더 생겨 뒤가 전부 밀린다. 그걸 보려면 따옴표를
    // 아는 파서로 세야 한다 — split(",")는 따옴표 안 쉼표도 쪼갠다.
    const cells = parseCsvRow(row);
    expect(cells).toHaveLength(parseCsvRow(head).length);
    expect(cells[9]).toBe(detail);          // 쉼표가 든 값이 한 칸에 온전히
  });

  test("칸 수가 머리글과 같다", () => {
    const cells = parseCsvRow(toCsv([item()], {}).split("\n")[1]);
    expect(cells).toHaveLength(11);
    expect(parseCsvRow(toCsv([item()], {}).split("\n")[0])).toHaveLength(11);
  });

  test("따옴표는 겹따옴표로 escape 한다", () => {
    const row = toCsv([item({ image: 'a".png' })], {}).split("\n")[1];
    expect(row).toContain('"a"".png"');
    // 되읽었을 때 원래 값으로 돌아와야 진짜 escape다
    expect(parseCsvRow(row)[1]).toBe('a".png');
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

describe("saveStatusMessage — 저장 실패가 드러나는가 (docs/24 B1)", () => {
  test("둘 다 성공이면 아무 말도 안 한다", () => {
    expect(saveStatusMessage(false, false)).toBe("");
  });

  test("서버만 실패하면 '다른 기계에서 못 이어받는다'를 말한다", () => {
    const m = saveStatusMessage(true, false);
    expect(m).toContain("서버");
    expect(m).toContain("다른 기계");
  });

  test("브라우저만 실패하면 서버에는 남았다고 말한다", () => {
    expect(saveStatusMessage(false, true)).toContain("서버에는 남았습니다");
  });

  test("둘 다 실패하면 사라진다고 말한다", () => {
    expect(saveStatusMessage(true, true)).toContain("사라집니다");
  });
});

describe("열기 → 판정 → 새로고침 → 복원 → CSV (docs/24 B2)", () => {
  beforeEach(() => localStorage.clear());

  // B1에서 고친 그 상황을 흐름 전체로 다시 확인한다 — 한 이미지에 누락 후보 둘.
  const a = item({ label_index: null, suspicion: "missing", label: "라벨 누락 의심",
                   box: [10, 20, 60, 70], rank: 1 });
  const b = item({ label_index: null, suspicion: "missing", label: "라벨 누락 의심",
                   box: [200, 30, 260, 90], rank: 2 });

  test("하나만 판정하면 하나만 남는다", () => {
    expect(saveVerdicts("ds9", { [keyOf(a)]: "hit" })).toBe(true);
    const restored = loadVerdicts("ds9");           // 새로고침
    expect(restored[keyOf(a)]).toBe("hit");
    expect(restored[keyOf(b)]).toBeUndefined();     // 이웃으로 안 번진다
  });

  test("복원한 판정이 CSV에 그대로 나온다", () => {
    saveVerdicts("ds9", { [keyOf(a)]: "hit" });
    const rows = toCsv([a, b], loadVerdicts("ds9")).split("\n");
    expect(rows).toHaveLength(3);                   // 머리글 + 두 줄
    expect(rows[1]).toContain("오류 맞음");
    expect(rows[2].endsWith(",")).toBe(true);       // 판정 칸이 비어 있다
  });

  test("CSV의 좌표가 후보의 좌표와 같다", () => {
    // 받는 쪽은 라벨링 도구다. 좌표가 어긋나면 엉뚱한 박스를 연다.
    const rows = toCsv([a, b], {}).split("\n");
    expect(rows[1]).toContain("10.0,20.0,60.0,70.0");
    expect(rows[2]).toContain("200.0,30.0,260.0,90.0");
  });

  test("누락 의심에도 좌표가 나온다", () => {
    // '있어야 할 자리'인 예측 박스다. 이게 없으면 누락 후보를 찾아갈 수 없다.
    expect(toCsv([a], {}).split("\n")[1]).not.toContain(",,,,");
  });

  test("판정을 지우면 CSV에서도 빈다", () => {
    saveVerdicts("ds9", { [keyOf(a)]: "hit" });
    saveVerdicts("ds9", {});                        // 같은 값을 다시 눌렀다
    expect(toCsv([a], loadVerdicts("ds9")).split("\n")[1].endsWith(",")).toBe(true);
  });
});

describe("csvScopeNote — 전체인가 일부인가 (docs/24 B2)", () => {
  test("거르지 않았으면 전체라고 말한다", () => {
    expect(csvScopeNote(22, 22)).toContain("전체 22건");
  });

  test("걸렀으면 일부라고 말하고 전체 수도 알려준다", () => {
    const m = csvScopeNote(3, 22);
    expect(m).toContain("보이는 3건만");
    expect(m).toContain("전체 22건");
  });
});

describe("makeVerdictSender — 저장을 한 줄로 세운다 (docs/25 R2)", () => {
  test("앞 요청이 끝나기 전에는 다음을 안 보낸다", async () => {
    const sent: string[] = [];
    let release!: () => void;
    const send = (v: Verdicts) => {
      sent.push(Object.keys(v).join(","));
      return new Promise<void>((r) => { release = r; });
    };
    const put = makeVerdictSender(send);

    void put({ a: "hit" });
    void put({ a: "hit", b: "hit" });
    expect(sent).toEqual(["a"]);          // 두 번째는 아직 안 나갔다

    release();
    await Promise.resolve();
    await Promise.resolve();
    expect(sent).toEqual(["a", "a,b"]);
  });

  test("기다리는 동안 쌓인 중간 상태는 건너뛴다", async () => {
    // 전체 교체 API라 중간 것을 보낼 이유가 없다.
    const sent: string[] = [];
    let release!: () => void;
    const send = (v: Verdicts) => {
      sent.push(Object.keys(v).join(","));
      return new Promise<void>((r) => { release = r; });
    };
    const put = makeVerdictSender(send);

    void put({ a: "hit" });
    void put({ a: "hit", b: "hit" });
    void put({ a: "hit", b: "hit", c: "hit" });
    release();
    await Promise.resolve();
    await Promise.resolve();
    expect(sent).toEqual(["a", "a,b,c"]);   // 가운데는 안 보낸다
  });

  test("실패하면 false를 돌려주되 줄은 계속 흐른다", async () => {
    let n = 0;
    const put = makeVerdictSender(() => {
      n += 1;
      return n === 1 ? Promise.reject(new Error("끊김")) : Promise.resolve();
    });
    expect(await put({ a: "hit" })).toBe(false);
    expect(await put({ a: "miss" })).toBe(true);
  });
})
