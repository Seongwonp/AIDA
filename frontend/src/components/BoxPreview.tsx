import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../api";

/**
 * 의심 박스를 이미지 위에 그려 보여준다.
 *
 * 목록만으로는 "000075.png의 1번 박스가 28% 작다"까지만 알 수 있다. 검수자는
 * 그 이미지를 직접 열고 몇 번째 박스인지 세어야 했다. 여기서 바로 보이면
 * 대부분의 판단이 목록 안에서 끝난다.
 *
 * 박스 주변만 잘라서 보여준다 — 전체 이미지를 축소하면 작은 상자는 몇 픽셀이
 * 되어 아무것도 안 보인다. KITTI 자동차 중앙값이 81×48px, COCO는 38×27px다.
 */

const PAD = 1.6;        // 박스 크기의 몇 배까지 주변을 보여줄지
const VIEW = 200;       // 미리보기 한 변(px)

export function BoxPreview({ datasetId, image, box }:
                           { datasetId: string; image: string; box: number[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    let cancelled = false;

    img.onload = () => {
      if (cancelled) return;
      const [x1, y1, x2, y2] = box;
      const bw = Math.max(x2 - x1, 1);
      const bh = Math.max(y2 - y1, 1);
      // 정사각형으로 잘라야 미리보기에서 비율이 안 망가진다
      const side = Math.max(bw, bh) * PAD;
      const cx = (x1 + x2) / 2;
      const cy = (y1 + y2) / 2;
      // 이미지 밖으로 나가지 않게 가둔다
      const sx = Math.max(0, Math.min(cx - side / 2, img.width - side));
      const sy = Math.max(0, Math.min(cy - side / 2, img.height - side));
      const sw = Math.min(side, img.width);
      const sh = Math.min(side, img.height);

      ctx.imageSmoothingEnabled = false;   // 확대해도 뭉개지지 않게
      ctx.clearRect(0, 0, VIEW, VIEW);
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, VIEW, VIEW);

      // 잘라낸 영역 기준으로 박스를 다시 계산해 그린다
      const k = VIEW / sw;
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ccff00";
      ctx.strokeRect((x1 - sx) * k, (y1 - sy) * k, bw * k, bh * k);
      // 네온만으로는 밝은 배경에서 안 보여서 검은 테두리를 덧그린다
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(0,0,0,0.85)";
      ctx.strokeRect((x1 - sx) * k - 1.5, (y1 - sy) * k - 1.5, bw * k + 3, bh * k + 3);
    };
    img.onerror = () => { if (!cancelled) setFailed(true); };
    img.src = `${API_BASE_URL}/api/datasets/${datasetId}/images/${encodeURIComponent(image)}`;

    return () => { cancelled = true; };
  }, [datasetId, image, box]);

  if (failed) {
    return <span className="preview-missing" title={image}>이미지 없음</span>;
  }
  return (
    <canvas
      ref={canvasRef}
      className="box-preview"
      width={VIEW}
      height={VIEW}
      aria-label={`${image}의 의심 박스 미리보기`}
    />
  );
}
