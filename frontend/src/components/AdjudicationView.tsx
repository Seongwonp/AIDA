import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { API_BASE_URL, getLabelBoxes, type LabelBox } from "../api";
import { cropRegion, type Region } from "./adjudicationCrop";

/**
 * 판정용 이미지 — **후보 박스와 주변 기존 라벨을 구분해서** 보여준다.
 *
 * 재검수 화면의 `BoxPreview`는 박스 하나만 잘라 보여준다. 그걸로는 **판정할 수
 * 없다.**
 *
 * - 기존 라벨을 볼 때: 이 박스가 객체를 잘 감쌌는지 보려면 **객체 전체**와
 *   그 주변이 보여야 한다. 박스에 딱 맞춰 자르면 넘치는지 모자라는지가 안 보인다.
 * - 누락 후보를 볼 때: 그 자리에 객체가 있는지, 그리고 **이미 라벨된 것이
 *   아닌지**를 봐야 한다. 주변 라벨이 안 보이면 "이미 라벨돼 있는데 누락이라고
 *   하는 것"과 구분할 수 없다.
 *
 * 그래서 넓게 자르고, **후보 박스와 기존 라벨을 다른 색으로** 그린다.
 *
 * 자르는 창은 **원본 이미지와 같은 가로세로 비율**이다 — 예전에는 정사각형으로 잘라 정사각형
 * 캔버스에 그려, 이미지 끝에서 창이 줄어들면 그림이 찌그러졌다. 화면 폭은 최대 `VIEW_MAX`(CSS px)이고
 * 좁은 화면에서는 폭에 맞춰 줄어든다. 캔버스는 `devicePixelRatio`배 해상도로 그려 선명하게 둔다.
 * 그림을 누르거나 초점을 두고 Enter를 누르면 **원본 전체**를 같은 박스와 함께 크게 본다.
 */

// 그림 폭의 상한(CSS px). **판정 버튼이 스크롤 없이 보여야 한다** — 넓은 화면에서는 그림 옆에
// 단추를 두고(App.css `.judge-split`), 1366×768에서도 첫 화면에 단추가 들어온다.
export const VIEW_MAX = 500;
const MAX_BACKING = 4096; // 캔버스 한 변의 상한(장치 픽셀) — 큰 원본·높은 배율에서 메모리를 막는다

export const CANDIDATE_COLOR = "#e11d48";   // 지금 보는 **기존 라벨**
export const CONTEXT_COLOR = "#2563eb";     // 이미 라벨된 것
// **누락은 색까지 다르게 한다.** timing1 리허설에서 누락 후보 4건 중 2건이
// 겹치는 파란 박스도 없는데 빠르게 "오류 아니었다"(지금의 "오류 없음")로 판정됐다 — 빨간 점선을
// "지금 보는 라벨"로 읽고 박스 품질을 답한 것으로 보인다. **표본 4건이라
// 확인된 원인은 아니지만**, 두 질문을 색으로 갈라 두는 편이 안전하다.
export const MISSING_COLOR = "#d97706";

function pixelRatio(): number {
  const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio;
  return Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
}

/**
 * 그림 하나를 그린다. `outW×outH`는 캔버스의 장치 픽셀, `k`는 CSS px 하나가 장치 픽셀 몇 개인지 —
 * 선 굵기·글자 크기를 화면에서 같은 굵기로 보이게 한다.
 */
function drawScene(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  region: Region,
  outW: number,
  outH: number,
  k: number,
  labels: LabelBox[],
  box: number[],
  labelIndex: number | null,
) {
  const { sx, sy, sw, sh } = region;
  ctx.imageSmoothingEnabled = true;
  ctx.clearRect(0, 0, outW, outH);
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, outW, outH);

  const toView = (px: number, py: number): [number, number] => [
    ((px - sx) / sw) * outW,
    ((py - sy) / sh) * outH,
  ];
  const stroke = (
    rect: [number, number, number, number],
    color: string,
    lineWidth: number,
    dashed: boolean,
  ) => {
    const [ax, ay] = toView(rect[0], rect[1]);
    const [bx, by] = toView(rect[2], rect[3]);
    ctx.setLineDash(dashed ? [7 * k, 5 * k] : []);
    ctx.lineWidth = lineWidth * k;
    ctx.strokeStyle = color;
    ctx.strokeRect(ax, ay, bx - ax, by - ay);
  };

  // 먼저 기존 라벨(파랑), 그 위에 후보(빨강) — 겹쳐도 후보가 보이게.
  labels.forEach((label, index) => {
    if (labelIndex !== null && index === labelIndex) return;  // 후보가 그린다
    const [ncx, ncy, nw, nh] = label.box;
    stroke([
      (ncx - nw / 2) * img.width, (ncy - nh / 2) * img.height,
      (ncx + nw / 2) * img.width, (ncy + nh / 2) * img.height,
    ], CONTEXT_COLOR, 2, false);
  });
  const [x1, y1, x2, y2] = box;
  const missing = labelIndex === null;
  stroke([x1, y1, x2, y2], missing ? MISSING_COLOR : CANDIDATE_COLOR, 3, missing);
  ctx.setLineDash([]);

  if (missing) {
    // 박스 위에 무엇을 묻는지 적는다. 색과 점선만으로는 "지금 보는 라벨"과
    // 헷갈릴 수 있다.
    const [bx, ty] = toView(x1, y1);
    const text = "라벨 없음?";
    ctx.font = `bold ${14 * k}px sans-serif`;
    const pad = 4 * k;
    const tagW = ctx.measureText(text).width + pad * 2;
    // 박스가 그림 오른쪽 끝에 붙으면 글자가 잘려 "라벨 없"만 보였다 — 그림 안으로 당긴다.
    const tx = Math.max(0, Math.min(bx, outW - tagW));
    const top = Math.max(0, ty - 20 * k);
    ctx.fillStyle = MISSING_COLOR;
    ctx.fillRect(tx, top, tagW, 18 * k);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(text, tx + pad, top + 13 * k);
  }
}

export function AdjudicationView({
  datasetId,
  image,
  box,
  labelIndex,
  className,
}: {
  datasetId: string;
  image: string;
  /** 후보 박스, 원본 픽셀 좌표 (x1, y1, x2, y2). */
  box: number[] | null;
  /** 기존 라벨을 보는 중이면 그 라벨의 번호. 누락이면 `null`. */
  labelIndex: number | null;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [labels, setLabels] = useState<LabelBox[]>([]);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [full, setFull] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLabels([]);
    // 문맥이 없어도 판정은 이어져야 한다 — 못 불러오면 후보 박스만 그린다.
    getLabelBoxes(datasetId, image)
      .then((data) => !cancelled && setLabels(data.labels))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [datasetId, image]);

  // 그리기는 최신 값으로 한다 — 이미지가 늦게 와도, 라벨이 늦게 와도 같은 함수가 그린다.
  const drawRef = useRef<() => void>(() => undefined);
  drawRef.current = () => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !box) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const region = cropRegion(box, img.width, img.height);
    const dpr = pixelRatio();
    const outW = Math.min(MAX_BACKING, Math.round(VIEW_MAX * dpr));
    const outH = Math.max(1, Math.round(outW * (region.sh / region.sw)));
    if (canvas.width !== outW) canvas.width = outW;
    if (canvas.height !== outH) canvas.height = outH;
    drawScene(ctx, img, region, outW, outH, outW / VIEW_MAX, labels, box, labelIndex);
  };

  useEffect(() => {
    if (!box) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    let cancelled = false;
    imgRef.current = null;
    setReady(false);
    setFailed(false);
    img.onload = () => {
      if (cancelled) return;
      imgRef.current = img;
      drawRef.current();
      setReady(true);
    };
    img.onerror = () => !cancelled && setFailed(true);
    img.src = `${API_BASE_URL}/api/datasets/${datasetId}/images/${encodeURIComponent(image)}`;
    return () => {
      cancelled = true;
    };
  }, [datasetId, image, box]);

  // 라벨이 오거나 후보가 바뀌면 다시 그린다(이미지가 아직이면 `drawRef`가 아무것도 안 한다).
  useEffect(() => {
    drawRef.current();
  }, [labels, box, labelIndex]);

  const closeFull = useCallback(() => {
    setFull(false);
    // 연 자리로 초점을 돌려준다.
    triggerRef.current?.focus();
  }, []);

  if (!box) return null;
  if (failed) {
    return (
      <p className="warn" role="alert">
        이미지를 불러오지 못했습니다. 이 후보는 판정하지 말고 넘어가세요.
      </p>
    );
  }

  return (
    <figure className={className}>
      <button
        type="button"
        ref={triggerRef}
        className="adj-zoom"
        aria-label="전체 이미지 크게 보기"
        aria-haspopup="dialog"
        disabled={!ready}
        onClick={() => setFull(true)}
      >
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={`${image}의 판정 대상 박스와 주변 기존 라벨`}
        />
      </button>
      {/* 색은 표시(▬)에만 쓰고 글자는 본문 색으로 둔다 — 주황·파랑 글자는 흰 바탕·어두운 바탕에서
          글자 대비(4.5:1)를 못 채웠다. 한 줄에 한 항목씩 둔다. */}
      <figcaption className="adj-legend">
        <Legend labelIndex={labelIndex} />
        <span className="adj-zoom-hint">그림을 누르거나 Enter — 전체 이미지</span>
      </figcaption>
      {full && imgRef.current && (
        <FullView
          img={imgRef.current}
          image={image}
          box={box}
          labels={labels}
          labelIndex={labelIndex}
          onClose={closeFull}
        />
      )}
    </figure>
  );
}

function Legend({ labelIndex }: { labelIndex: number | null }) {
  return (
    <>
      {labelIndex === null ? (
        <span>
          <span className="adj-mark" style={{ color: MISSING_COLOR }} aria-hidden="true">▬</span>
          주황 점선 = <strong>이 객체의 라벨이 누락됐는가</strong> (박스 품질을 보는 것이 아닙니다)
        </span>
      ) : (
        <span>
          <span className="adj-mark" style={{ color: CANDIDATE_COLOR }} aria-hidden="true">▬</span>
          빨강 실선 = <strong>지금 보는 라벨</strong>
        </span>
      )}
      <span>
        <span className="adj-mark" style={{ color: CONTEXT_COLOR }} aria-hidden="true">▬</span>
        파랑 = 이미 붙어 있는 다른 라벨
      </span>
    </>
  );
}

/**
 * 원본 전체를 같은 박스와 함께 크게 보는 대화 상자.
 *
 * - Esc·닫기 단추·바깥(어두운 면) 클릭으로 닫는다. 닫으면 그림 단추로 초점이 돌아간다.
 * - Tab은 대화 상자 안에서만 돈다. 떠 있는 동안 판정 단축키(1·2·3·←·→)는 판정 화면이 무시한다
 *   (`aria-modal` 확인).
 */
function FullView({
  img,
  image,
  box,
  labels,
  labelIndex,
  onClose,
}: {
  img: HTMLImageElement;
  image: string;
  box: number[];
  labels: LabelBox[];
  labelIndex: number | null;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [view, setView] = useState(() => fitView(img));

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    const onResize = () => setView(fitView(img));
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, [img, onClose]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = pixelRatio();
    const outW = Math.min(MAX_BACKING, Math.round(view.w * dpr));
    const outH = Math.max(1, Math.round(outW * (img.height / img.width)));
    canvas.width = outW;
    canvas.height = outH;
    drawScene(ctx, img, { sx: 0, sy: 0, sw: img.width, sh: img.height }, outW, outH,
              outW / view.w, labels, box, labelIndex);
  }, [img, view, labels, box, labelIndex]);

  const trapTab = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab") return;
    const items = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled)") ?? [],
    );
    if (items.length === 0) return;
    const first = items[0];
    const end = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || !dialogRef.current?.contains(active))) {
      e.preventDefault();
      end.focus();
    } else if (!e.shiftKey && (active === end || !dialogRef.current?.contains(active))) {
      e.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <div
      className="adj-full-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="adj-full-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adj-full-title"
        ref={dialogRef}
        onKeyDown={trapTab}
      >
        <div className="adj-full-head">
          <h3 id="adj-full-title">전체 이미지</h3>
          <button type="button" ref={closeRef} className="judge-nav-button" onClick={onClose}>
            닫기 (Esc)
          </button>
        </div>
        <canvas
          ref={canvasRef}
          className="adj-full-canvas"
          style={{ inlineSize: `${view.w}px`, blockSize: `${view.h}px` }}
          role="img"
          aria-label={`${image} 전체와 판정 대상 박스, 기존 라벨`}
        />
        <p className="adj-legend adj-full-legend">
          <Legend labelIndex={labelIndex} />
        </p>
      </div>
    </div>,
    document.body,
  );
}

/** 창 안에 들어가는 전체 그림 크기(CSS px). 원본보다 키우지 않는다. */
function fitView(img: HTMLImageElement): { w: number; h: number } {
  const vw = typeof window === "undefined" ? 1280 : window.innerWidth;
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  const maxW = Math.max(160, vw - 64);
  const maxH = Math.max(120, vh - 170);
  const s = Math.min(1, maxW / img.width, maxH / img.height);
  return { w: Math.round(img.width * s), h: Math.round(img.height * s) };
}
