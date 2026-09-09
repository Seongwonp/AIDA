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
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const getLabelBoxes = vi.fn();
vi.mock("../api", () => ({
  getLabelBoxes: (...a: unknown[]) => getLabelBoxes(...a),
  API_BASE_URL: "http://backend",
}));

import { AdjudicationView, CANDIDATE_COLOR, CONTEXT_COLOR } from "./AdjudicationView";

/** 그려진 사각형을 색깔·점선과 함께 모은다. */
type Drawn = { color: string; dashed: boolean; rect: number[] };

let drawn: Drawn[];
let loadImage: (() => void) | null;

beforeEach(() => {
  drawn = [];
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
    drawImage: () => undefined,
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

  test("누락 후보는 점선으로 그린다", async () => {
    // "여기 있어야 한다"와 "여기 붙어 있다"는 다른 말이다.
    show({ labelIndex: null });
    await waitFor(() => expect(loadImage).toBeTruthy());
    loadImage!();

    const candidate = drawn.find((d) => d.color === CANDIDATE_COLOR);
    expect(candidate?.dashed).toBe(true);
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

  test("누락 후보에는 다른 문구를 쓴다", async () => {
    show({ labelIndex: null });
    expect(screen.getByText(/빠졌다고 지목된 자리/)).toBeTruthy();
  });
});
