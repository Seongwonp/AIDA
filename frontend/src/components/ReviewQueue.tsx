import { useMemo, useState } from "react";
import { BoxPreview } from "./BoxPreview";
import type { ReviewQueueItem } from "../types";

/**
 * 재검수 대기열 — 이 제품이 실제로 내놓는 결과물.
 *
 * 예전에는 상위 20개를 그냥 표로 찍기만 했다. 그러면 화면에서 읽을 수는 있어도
 * **일을 할 수가 없다.** 검수자는 목록을 들고 하나씩 고쳐 나가는 사람이라
 * 최소한 세 가지가 필요하다:
 *
 *   - 유형으로 좁히기 (오늘은 누락만 보겠다)
 *   - 다 본 것 표시하기 (어디까지 했는지)
 *   - 내보내기 (라벨 도구나 스프레드시트로 옮기기)
 *
 * 체크 상태는 브라우저에만 남긴다(localStorage). 서버에 검수 진행을 저장하려면
 * 사용자 개념이 필요한데 지금 제품에는 없다. 데이터셋 id로 키를 나눠, 다른
 * 데이터셋의 진행과 섞이지 않게 한다.
 */

function loadDone(datasetId: string): Set<string> {
  try {
    const raw = localStorage.getItem(`aida-reviewed-${datasetId}`);
    return new Set<string>(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();               // 사생활 보호 모드 등에서 막힐 수 있다
  }
}

function keyOf(item: ReviewQueueItem): string {
  return `${item.image}#${item.label_index ?? "none"}#${item.suspicion}`;
}

function toCsv(items: ReviewQueueItem[], done: Set<string>): string {
  const head = ["순위", "이미지", "라벨 인덱스", "의심 유형", "심각도", "근거", "검토함"];
  const esc = (v: string | number) => {
    const s = String(v);
    // 쉼표·따옴표·줄바꿈이 들어 있으면 감싸야 한 칸으로 읽힌다
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = items.map((i) => [
    i.rank, i.image, i.label_index ?? "", i.label,
    i.severity.toFixed(3), i.detail, done.has(keyOf(i)) ? "Y" : "",
  ].map(esc).join(","));
  // 엑셀이 UTF-8 CSV를 한글로 열려면 BOM이 필요하다
  return "﻿" + [head.join(","), ...rows].join("\n");
}

export function ReviewQueue({ items, datasetId }:
                            { items: ReviewQueueItem[]; datasetId: string }) {
  const [type, setType] = useState("");
  const [query, setQuery] = useState("");
  const [done, setDone] = useState<Set<string>>(() => loadDone(datasetId));
  const [onlyOpen, setOnlyOpen] = useState(false);
  // 미리보기는 이미지를 내려받으므로 기본으로 켜두면 목록이 큰 데이터셋에서
  // 수십 장을 한꺼번에 받는다. 필요할 때 켜게 한다.
  const [preview, setPreview] = useState(false);

  const types = useMemo(() => {
    const seen = new Map<string, string>();
    items.forEach((i) => seen.set(i.suspicion, i.label));
    return [...seen.entries()];
  }, [items]);

  const shown = useMemo(() => items.filter((i) => {
    if (type && i.suspicion !== type) return false;
    if (onlyOpen && done.has(keyOf(i))) return false;
    if (query && !i.image.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  }), [items, type, query, done, onlyOpen]);

  const toggle = (item: ReviewQueueItem) => {
    const next = new Set(done);
    const k = keyOf(item);
    next.has(k) ? next.delete(k) : next.add(k);
    setDone(next);
    try {
      localStorage.setItem(`aida-reviewed-${datasetId}`, JSON.stringify([...next]));
    } catch {
      /* 저장 못 해도 이번 세션에는 반영된다 */
    }
  };

  const download = () => {
    const blob = new Blob([toCsv(shown, done)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aida_재검수목록_${datasetId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const doneCount = items.filter((i) => done.has(keyOf(i))).length;
  const pct = items.length ? (doneCount / items.length) * 100 : 0;

  return (
    <>
      <div className="queue-toolbar">
        <div className="queue-progress" title={`${doneCount} / ${items.length}`}>
          <div className="queue-progress-bar">
            <div className="queue-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="queue-progress-text">
            {doneCount} / {items.length} 검토함
          </span>
        </div>

        <div className="queue-controls">
          <label className="sr-only" htmlFor="queue-type">의심 유형으로 좁히기</label>
          <select id="queue-type" className="profile-select" value={type}
                  onChange={(e) => setType(e.target.value)}>
            <option value="">유형 전체</option>
            {types.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>

          <label className="sr-only" htmlFor="queue-search">이미지 이름으로 찾기</label>
          <input id="queue-search" className="queue-search" placeholder="이미지 이름"
                 value={query} onChange={(e) => setQuery(e.target.value)} />

          <label className="queue-check">
            <input type="checkbox" checked={onlyOpen}
                   onChange={(e) => setOnlyOpen(e.target.checked)} />
            안 본 것만
          </label>

          <label className="queue-check">
            <input type="checkbox" checked={preview}
                   onChange={(e) => setPreview(e.target.checked)} />
            미리보기
          </label>

          <button className="refresh-button" onClick={download}
                  disabled={shown.length === 0}>
            CSV 내려받기
          </button>
        </div>
      </div>

      {shown.length === 0 ? (
        <p className="report-caveat">조건에 맞는 항목이 없습니다.</p>
      ) : (
        <div className="table-scroll">
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col" aria-label="검토함" />
                <th scope="col">#</th>
                <th scope="col">이미지</th>
                <th scope="col">라벨</th>
                <th scope="col">의심 유형</th>
                <th scope="col">근거</th>
                {preview && <th scope="col">미리보기</th>}
              </tr>
            </thead>
            <tbody>
              {shown.map((item) => {
                const checked = done.has(keyOf(item));
                return (
                  <tr key={keyOf(item)} className={checked ? "row-done" : ""}>
                    <td>
                      <input type="checkbox" checked={checked}
                             onChange={() => toggle(item)}
                             aria-label={`${item.image} 검토함으로 표시`} />
                    </td>
                    <td>{item.rank}</td>
                    <td>{item.image}</td>
                    <td>{item.label_index ?? "—"}</td>
                    <td>{item.label}</td>
                    <td>{item.detail}</td>
                    {preview && (
                      <td>
                        {item.box ? (
                          <BoxPreview datasetId={datasetId} image={item.image}
                                      box={item.box} />
                        ) : (
                          <span className="preview-missing">좌표 없음</span>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
