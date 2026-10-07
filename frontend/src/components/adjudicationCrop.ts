/**
 * 판정용 그림의 자르는 창 (AdjudicationView). 컴포넌트 파일과 나눠 둔다 — 순수 계산이라 따로 검사한다.
 */

const PAD = 3.2;       // 후보 박스 크기의 몇 배까지 주변을 보여줄지
const MIN_SPAN = 260;  // 너무 좁게 잘리지 않게 하는 최소 폭(원본 픽셀)

export type Region = { sx: number; sy: number; sw: number; sh: number };

/**
 * 후보 주변을 자를 창. 원본과 같은 비율로, 짧은 변이 `max(박스 긴 변 × PAD, MIN_SPAN)` 이상이다.
 * 이미지보다 커지면 비율을 지킨 채 이미지에 맞게 줄이고, 이미지 밖으로 나가지 않게 민다.
 */
export function cropRegion(box: number[], imgW: number, imgH: number): Region {
  const [x1, y1, x2, y2] = box;
  const side = Math.max(Math.max(x2 - x1, y2 - y1) * PAD, MIN_SPAN);
  const aspect = imgW / imgH;
  let sw = aspect >= 1 ? side * aspect : side;
  let sh = aspect >= 1 ? side : side / aspect;
  const fit = Math.min(1, imgW / sw, imgH / sh);
  sw *= fit;
  sh *= fit;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const sx = Math.max(0, Math.min(cx - sw / 2, imgW - sw));
  const sy = Math.max(0, Math.min(cy - sh / 2, imgH - sh));
  return { sx, sy, sw, sh };
}
