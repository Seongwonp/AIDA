/**
 * 판정용 이미지 화면 (docs/manual-timing-pilot.md).
 *
 * **이 화면이 판정 시간의 전부다.** 볼 것이 없으면 전부 "모르겠다"가 되고,
 * 그렇게 나온 시간은 판정 시간이 아니라 버튼 클릭 시간이다. 처음 파일럿이
 * 실제로 그랬다.
 *
 * jsdom에는 canvas 구현이 없으므로 **무엇을 그렸는지**를 2D 컨텍스트 호출로
 * 확인한다. 실제 픽셀은 브라우저에서 눈으로 본다.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const getLabelBoxes = vi.fn();
vi.mock("../api", () => ({
  getLabelBoxes: (...a: unknown[]) => getLabelBoxes(...a),
  API_BASE_URL: "http://backend",
}));

import { AdjudicationView, CANDIDATE_COLOR, CONTEXT_COLOR,
         MISSING_COLOR, VIEW_MAX } from "./AdjudicationView";
import { cropRegion } from "./adjudicationCrop";

/** 그려진 사각형을 색깔·점선과 함께 모은다. */
type Drawn = { color: string; dashed: boolean; rect: number[] };

let drawn: Drawn[];
/** drawImage 호출 인자(원본 sx, sy, sw, sh, 대상 dx, dy, dw, dh). */
let images: number[][];
let loadImage: (() => void) | null;

beforeEach(() => {
  drawn = [];
  images = [];
  loadImage = null;
  getLabelBoxes.mockResolvedValue({ image: "a.jpg", labels: [] });

  const context = {
    strokeStyle: "",
    lineWidth: 0,
    imageSmoothingEnabled: false,
    dash: [] as number[],
    setLineDash(dash: number[]) {
      this.dash = dash;
    },
    strokeRect(x: number, y: number, w: number, h: number) {
      drawn.push({ color: this.strokeStyle, dashed: this.dash.length > 0,
                   rect: [x, y, w, h] });
    },
    clearRect: () => undefined,
    drawImage: (_img: unknown, ...a: number[]) => void images.push(a),
    fillStyle: "",
    font: "",
    fillRect: () => undefined,
    fillText: () => undefined,
    measureText: (text: string) => ({ width: text.length * 7 }),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockReturnValue(context as unknown as CanvasRenderingContext2D);

  // 이미지 로딩을 검사가 쥔다.
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    crossOrigin = "";
    width = 1000;
    height = 800;
    naturalWidth = 1000;
    naturalHeight = 800;
    set src(_value: string) {
      loadImage = () => this.onload?.();
    }
  }
  vi.stubGlobal("Image", FakeImage);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function show(over: Partial<Parameters<typeof AdjudicationView>[0]> = {}) {
  return render(
    <AdjudicationView datasetId="ds1" image="a.jpg" box={[400, 300, 500, 400]}
                      labelIndex={0} {...over} />,
  );
}

describe("무엇을 그리는가", () => {
  test("후보 박스를 그린다", async () => {
    show();
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();

    const candidate = drawn.filter((d) => d.color === CANDIDATE_COLOR);
    expect(candidate).toHaveLength(1);
  });

  test("이미 붙어 있는 다른 라벨을 다른 색으로 그린다", async () => {
    // 주변이 안 보이면 "이미 라벨돼 있는데 누락이라고 하는 것"과 구분할 수 없다.
    getLabelBoxes.mockResolvedValue({
      image: "a.jpg",
      labels: [
        { label_index: 0, class_id: 0, class_name: "Car", box: [0.45, 0.44, 0.1, 0.12] },
        { label_index: 1, class_id: 0, class_name: "Car", box: [0.6, 0.5, 0.1, 0.1] },
        { label_index: 2, class_id: 0, class_name: "Car", box: [0.2, 0.3, 0.1, 0.1] },
      ],
    });
    show({ labelIndex: 0 });
    await waitFor(() => expect(getLabelBoxes).toHaveBeenCalled());
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();

    await waitFor(() => {
      // 판정 대상(0번)은 후보 색으로 한 번만 그린다 — 두 번 그리면 색이 겹친다.
      expect(drawn.filter((d) => d.color === CONTEXT_COLOR)).toHaveLength(2);
      expect(drawn.filter((d) => d.color === CANDIDATE_COLOR)).toHaveLength(1);
    });
  });

  test("누락 후보는 색도 다르고 점선이다", async () => {
    // timing1에서 누락 4건 중 2건이 빠르게 "오류 아니었다"로 판정됐다 —
    // 빨간 점선을 "지금 보는 라벨"로 읽고 박스 품질을 답한 것으로 보인다.
    show({ labelIndex: null });
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();

    const candidate = drawn.find((d) => d.color === MISSING_COLOR);
    expect(candidate?.dashed).toBe(true);
    // 기존 라벨 색을 쓰지 않는다 — 두 질문을 색으로 가른다.
    expect(drawn.find((d) => d.color === CANDIDATE_COLOR)).toBeUndefined();
  });

  test("기존 라벨 후보는 실선으로 그린다", async () => {
    show({ labelIndex: 0 });
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();

    expect(drawn.find((d) => d.color === CANDIDATE_COLOR)?.dashed).toBe(false);
  });
});

describe("문맥을 못 불러올 때", () => {
  test("판정은 이어진다", async () => {
    // 문맥이 없어도 후보 박스는 보여야 한다.
    getLabelBoxes.mockRejectedValue(new Error("끊김"));
    show();
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();

    expect(drawn.filter((d) => d.color === CANDIDATE_COLOR)).toHaveLength(1);
  });
});

describe("이미지를 못 불러올 때", () => {
  test("판정하지 말라고 말한다", async () => {
    // 안 보이는 것을 "오류 아니었다"로 누르면 그건 판정이 아니다.
    class FailingImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      crossOrigin = "";
      set src(_value: string) {
        setTimeout(() => this.onerror?.(), 0);
      }
    }
    vi.stubGlobal("Image", FailingImage);
    show();
    await screen.findByText(/이미지를 불러오지 못했습니다/);
  });
});

describe("범례", () => {
  test("두 색이 무엇인지 적는다", async () => {
    show({ labelIndex: 0 });
    expect(screen.getByText(/지금 보는 라벨/)).toBeTruthy();
    expect(screen.getByText(/이미 붙어 있는 다른 라벨/)).toBeTruthy();
  });

  test("누락 후보에는 무엇을 묻는지 적는다", async () => {
    show({ labelIndex: null });
    expect(screen.getByText(/이 객체의 라벨이 누락됐는가/)).toBeTruthy();
    expect(screen.getByText(/박스 품질을 보는/)).toBeTruthy();
  });
});

describe("누락 표시 글자", () => {
  test("박스가 그림 오른쪽 끝에 붙어도 '라벨 없음?' 표시가 그림 안에 들어온다", async () => {
    const fills: number[][] = [];
    const ctx = HTMLCanvasElement.prototype.getContext.call(document.createElement("canvas"), "2d") as unknown as {
      fillRect: (...a: number[]) => void;
    };
    ctx.fillRect = (...a: number[]) => void fills.push(a);
    // 이미지 오른쪽 끝(1000px)에 붙은 박스 — 자른 그림의 오른쪽 끝에 놓인다.
    show({ labelIndex: null, box: [990, 300, 1000, 360] });
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();

    expect(fills).toHaveLength(1);
    const [x, , w] = fills[0];
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x + w).toBeLessThanOrEqual(document.querySelector("canvas")!.width);
  });
});

describe("범례 대비", () => {
  test("색은 표시(▬)에만 쓰고 글자에는 쓰지 않는다", async () => {
    show({ labelIndex: null });
    const marks = Array.from(document.querySelectorAll(".adj-mark"));
    expect(marks.length).toBe(2);
    marks.forEach((m) => expect(m.getAttribute("aria-hidden")).toBe("true"));
    // 글자를 감싼 칸에는 색이 없다 — 주황·파랑 글자는 4.5:1을 못 채웠다.
    Array.from(document.querySelectorAll(".adj-legend > span")).forEach((s) => {
      expect((s as HTMLElement).style.color).toBe("");
    });
  });
});

describe("그림 크기와 비율", () => {
  test("자르는 창이 원본 비율을 따른다 — 정사각형으로 자르지 않는다", () => {
    // 1600×900(16:9) 원본, 작은 박스 → 짧은 변 260(MIN_SPAN), 긴 변 260×16/9.
    const r = cropRegion([800, 400, 840, 430], 1600, 900);
    expect(r.sw / r.sh).toBeCloseTo(1600 / 900, 6);
    expect(r.sh).toBeCloseTo(260, 6);
    // 이미지보다 큰 창은 비율을 지킨 채 이미지에 맞춘다.
    const big = cropRegion([0, 0, 1500, 880], 1600, 900);
    expect([big.sx, big.sy]).toEqual([0, 0]);
    expect(big.sw).toBeCloseTo(1600, 6);
    expect(big.sh).toBeCloseTo(900, 6);
    // 세로 사진도 같다.
    const tall = cropRegion([100, 100, 120, 140], 600, 1000);
    expect(tall.sw / tall.sh).toBeCloseTo(0.6, 6);
    // 창은 이미지 밖으로 나가지 않는다.
    const edge = cropRegion([1590, 880, 1600, 900], 1600, 900);
    expect(edge.sx + edge.sw).toBeLessThanOrEqual(1600);
    expect(edge.sy + edge.sh).toBeLessThanOrEqual(900);
  });

  test("캔버스는 원본 비율 그대로, devicePixelRatio배 해상도로 그린다", async () => {
    vi.stubGlobal("devicePixelRatio", 2);
    show();
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();
    const canvas = document.querySelector("canvas")!;
    expect(canvas.width).toBe(VIEW_MAX * 2);
    // FakeImage는 1000×800 — 그림도 5:4다(찌그러지지 않는다).
    expect(canvas.width / canvas.height).toBeCloseTo(1000 / 800, 2);
    const [sx, sy, sw, sh, dx, dy, dw, dh] = images.at(-1)!;
    expect(sw / sh).toBeCloseTo(dw / dh, 2);
    expect([dx, dy, dw, dh]).toEqual([0, 0, canvas.width, canvas.height]);
    expect(sx).toBeGreaterThanOrEqual(0);
    expect(sy).toBeGreaterThanOrEqual(0);
  });
});

describe("전체 이미지 보기", () => {
  async function loaded() {
    show();
    await waitFor(() => expect(loadImage).toBeTruthy());
    await act(async () => loadImage!());
    return screen.getByRole("button", { name: "전체 이미지 크게 보기" });
  }

  test("그림 단추에 접근 이름이 있고, 불러오기 전에는 못 누른다", async () => {
    show();
    const trigger = screen.getByRole("button", { name: "전체 이미지 크게 보기" });
    expect((trigger as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect(loadImage).toBeTruthy());
    await act(async () => loadImage!());
    expect((trigger as HTMLButtonElement).disabled).toBe(false);
  });

  test("누르면 원본 전체를 같은 박스와 함께 보여 주고, Esc로 닫으면 초점이 돌아온다", async () => {
    const trigger = await loaded();
    trigger.focus();
    const before = images.length;
    await act(async () => trigger.click());

    const dialog = screen.getByRole("dialog", { name: "전체 이미지" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    // 원본 전체(0,0,1000,800)를 그렸다.
    expect(images.slice(before).some(([sx, sy, sw, sh]) =>
      sx === 0 && sy === 0 && sw === 1000 && sh === 800)).toBe(true);
    // 후보 박스도 같이 그렸다.
    expect(drawn.filter((d) => d.color === CANDIDATE_COLOR).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("img", { name: /a\.jpg 전체/ })).toBeTruthy();
    // 초점은 대화 상자 안(닫기 단추)에 있다.
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "닫기 (Esc)" }));

    await act(async () => {
      fireEvent.keyDown(window, { key: "Escape" });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  test("Enter로도 열린다(단추 기본 동작)", async () => {
    const trigger = await loaded();
    // jsdom은 단추의 Enter → click을 흉내 내지 않는다 — 단추 요소라 브라우저가 해 준다는 것을 고정한다.
    expect(trigger.tagName).toBe("BUTTON");
    expect(trigger.getAttribute("type")).toBe("button");
    await act(async () => trigger.click());
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  test("Tab이 대화 상자 밖으로 나가지 않고, 닫기 단추·바깥 클릭으로 닫힌다", async () => {
    const trigger = await loaded();
    await act(async () => trigger.click());
    const close = screen.getByRole("button", { name: "닫기 (Esc)" });
    fireEvent.keyDown(close, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(close);

    await act(async () => close.click());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);

    await act(async () => trigger.click());
    const backdrop = document.querySelector(".adj-full-backdrop")!;
    await act(async () => {
      fireEvent.mouseDown(backdrop);
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
