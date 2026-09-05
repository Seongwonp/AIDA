import { useEffect, useState } from "react";
import { getDatasetHistory } from "../api";
import type { DatasetHistoryItem } from "../types";

/**
 * 지난 진단 목록.
 *
 * 새로고침하면 결과가 사라졌다. 디스크에는 그대로 있는데 화면에서 갈 방법이
 * 없어서, 쌓인 다섯 개를 아무도 못 봤다.
 *
 * 검수는 한 번에 끝나지 않는다 — 목록을 반쯤 보다가 내일 이어 보는 게
 * 정상이고(판정을 브라우저에 남기는 이유도 그것이다), 그러려면 어제 진단을
 * 다시 열 수 있어야 한다.
 */
export function HistoryCard({ onOpen }: { onOpen: (datasetId: string) => void }) {
  const [rows, setRows] = useState<DatasetHistoryItem[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getDatasetHistory()
      .then(setRows)
      .catch(() => setFailed(true));
  }, []);

  if (failed || rows.length === 0) return null;   // 처음 온 사람에게는 보일 게 없다

  return (
    <section className="card">
      <h2>지난 진단</h2>
      <p className="report-caveat">
        이 컴퓨터에서 진단한 데이터셋입니다. 열면 재검수 목록을 그대로 이어서
        볼 수 있습니다 — 판정 표시도 남아 있습니다.
      </p>
      <div className="table-scroll">
        <table className="report-table">
          <thead>
            <tr>
              <th scope="col">진단 시각</th>
              <th scope="col">이미지</th>
              <th scope="col">의심 건수</th>
              <th scope="col">가장 많은 유형</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.dataset_id}>
                <td>
                  {r.diagnosed_at
                    ? r.diagnosed_at.replace("T", " ").slice(0, 16)
                    : "—"}
                </td>
                <td>{r.num_images.toLocaleString()}장</td>
                <td>
                  {r.total_findings === null ? "—" : r.total_findings.toLocaleString()}
                </td>
                <td>{r.dominant_label ?? "—"}</td>
                <td>
                  {r.has_label_diagnosis ? (
                    <button className="refresh-button"
                            onClick={() => onOpen(r.dataset_id)}>
                      열기
                    </button>
                  ) : (
                    // 데이터셋 단위 진단만 있는 것 — 재검수 목록이 없다
                    <span className="preview-missing">재검수 목록 없음</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
