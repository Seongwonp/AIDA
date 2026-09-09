import { useEffect, useRef, useState } from "react";
import { API_BASE_URL, getLabelBoxes, type LabelBox } from "../api";

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
 */

// 한 변(px). **판정 버튼이 스크롤 없이 보여야 한다** — 후보마다 스크롤하면
// 시간이 늘고 엉뚱한 버튼을 누른다(docs/21 BC에서 겪은 것과 같은 종류).
const VIEW = 340;
const PAD = 3.2;       // 후보 박스 크기의 몇 배까지 주변을 보여줄지
const MIN_SPAN = 260;  // 너무 좁게 잘리지 않게 하는 최소 폭(원본 픽셀)

export const CANDIDATE_COLOR = "#e11d48";   // 지금 보는 **기존 라벨**
export const CONTEXT_COLOR = "#2563eb";     // 이미 라벨된 것
// **누락은 색까지 다르게 한다.** timing1 리허설에서 누락 후보 4건 중 2건이
// 겹치는 파란 박스도 없는데 빠르게 "오류 아니었다"로 판정됐다 — 빨간 점선을
// "지금 보는 라벨"로 읽고 박스 품질을 답한 것으로 보인다. **표본 4건이라
// 확인된 원인은 아니지만**, 두 질문을 색으로 갈라 두는 편이 안전하다.
export const MISSING_COLOR = "#d97706";

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
  const [labels, setLabels] = useState<LabelBox[]>([]);
  const [failed, setFailed] = useState(false);

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

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !box) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    let cancelled = false;

    img.onload = () => {
      if (cancelled) return;
      const [x1, y1, x2, y2] = box;
      // **후보 박스보다 넉넉히 넓게 자른다.** 딱 맞춰 자르면 박스가 객체를
      // 넘치는지 모자라는지 보이지 않는다.
      const side = Math.max(
        Math.max(x2 - x1, y2 - y1) * PAD,
        MIN_SPAN,
      );
      const cx = (x1 + x2) / 2;
      const cy = (y1 + y2) / 2;
      const sw = Math.min(side, img.width);
      const sh = Math.min(side, img.height);
      const sx = Math.max(0, Math.min(cx - sw / 2, img.width - sw));
      const sy = Math.max(0, Math.min(cy - sh / 2, img.height - sh));

      ctx.imageSmoothingEnabled = true;
      ctx.clearRect(0, 0, VIEW, VIEW);
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, VIEW, VIEW);

      const toView = (px: number, py: number): [number, number] => [
        ((px - sx) / sw) * VIEW,
        ((py - sy) / sh) * VIEW,
      ];
      const stroke = (
        rect: [number, number, number, number],
        color: string,
        width: number,
        dashed: boolean,
      ) => {
        const [ax, ay] = toView(rect[0], rect[1]);
        const [bx, by] = toView(rect[2], rect[3]);
        ctx.setLineDash(dashed ? [7, 5] : []);
        ctx.lineWidth = width;
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
      const missing = labelIndex === null;
      stroke([x1, y1, x2, y2], missing ? MISSING_COLOR : CANDIDATE_COLOR, 3,
             missing);
      ctx.setLineDash([]);

      if (missing) {
        // 박스 위에 무엇을 묻는지 적는다. 색과 점선만으로는 "지금 보는 라벨"과
        // 헷갈릴 수 있다.
        const [tx, ty] = toView(x1, y1);
        const text = "라벨 없음?";
        ctx.font = "bold 14px sans-serif";
        const pad = 4;
        const width = ctx.measureText(text).width + pad * 2;
        const top = Math.max(0, ty - 20);
        ctx.fillStyle = MISSING_COLOR;
        ctx.fillRect(tx, top, width, 18);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(text, tx + pad, top + 13);
      }
    };
    img.onerror = () => !cancelled && setFailed(true);
    img.src = `${API_BASE_URL}/api/datasets/${datasetId}/images/${encodeURIComponent(image)}`;

    return () => {
      cancelled = true;
    };
  }, [datasetId, image, box, labelIndex, labels]);

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
      <canvas
        ref={canvasRef}
        width={VIEW}
        height={VIEW}
        role="img"
        aria-label={`${image}의 판정 대상 박스와 주변 기존 라벨`}
      />
      <figcaption>
        {labelIndex === null ? (
          <span style={{ color: MISSING_COLOR }}>
            ▬ 주황 점선 = <strong>여기 라벨이 빠졌는가</strong> (박스 품질을 보는
            것이 아닙니다)
          </span>
        ) : (
          <span style={{ color: CANDIDATE_COLOR }}>
            ▬ 빨강 실선 = <strong>지금 보는 라벨</strong>
          </span>
        )}{" "}
        <span style={{ color: CONTEXT_COLOR }}>▬ 파랑 = 이미 붙어 있는 다른 라벨</span>
      </figcaption>
    </figure>
  );
}
