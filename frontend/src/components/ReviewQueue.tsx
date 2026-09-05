import { useEffect, useMemo, useRef, useState } from "react";
import { BoxPreview } from "./BoxPreview";
import type { ReviewQueueItem } from "../types";

/**
 * 재검수 대기열 — 이 제품이 실제로 내놓는 결과물.
 *
 * 예전에는 상위 20개를 그냥 표로 찍기만 했다. 그러면 화면에서 읽을 수는 있어도
 * **일을 할 수가 없다.** 검수자는 목록을 들고 하나씩 고쳐 나가는 사람이라
 * 최소한 이만큼이 필요하다:
 *
 *   - 유형으로 좁히기 (오늘은 누락만 보겠다)
 *   - 문제 박스를 눈으로 보기
 *   - **본 결과를 남기기** — 실제 오류였는지 아닌지
 *   - 내보내기 (라벨 도구나 스프레드시트로 옮기기)
 *
 * 세 번째가 특히 중요하다. "봤다"만 체크하면 검수자가 무엇을 알아냈는지가
 * 사라진다. 맞았는지 아닌지를 남기면 **이 데이터셋에서의 실제 정밀도**가
 * 나온다 — 우리가 KITTI에서 잰 94.0%가 아니라 고객 자기 숫자다.
 *
 * 판정은 브라우저에만 남긴다(localStorage). 서버에 저장하려면 사용자 개념이
 * 필요한데 지금 제품에는 없다. 데이터셋 id로 키를 나눠 섞이지 않게 한다.
 */

// 기본값 배열을 컴포넌트 안에 두면 렌더마다 새로 만들어져 참조가 달라진다
const NO_TYPES: string[] = [];

type Verdict = "hit" | "miss";           // 오류 맞음 | 오류 아님
type Verdicts = Record<string, Verdict>;

const STORE = (datasetId: string) => `aida-verdicts-${datasetId}`;
const LEGACY = (datasetId: string) => `aida-reviewed-${datasetId}`;

function loadVerdicts(datasetId: string): Verdicts {
  try {
    const raw = localStorage.getItem(STORE(datasetId));
    if (raw) return JSON.parse(raw) as Verdicts;
    // 이전 버전은 "봤다"만 배열로 저장했다. 그걸 버리지 않고 "판정 안 함"
    // 상태로 살려 온다 — 검수하던 사람의 진행이 업데이트로 날아가면 안 된다.
    const old = localStorage.getItem(LEGACY(datasetId));
    if (old) {
      const seen = JSON.parse(old) as string[];
      return Object.fromEntries(seen.map((k) => [k, "hit" as Verdict]));
    }
  } catch {
    /* 사생활 보호 모드 등에서 막힐 수 있다 */
  }
  return {};
}

function keyOf(item: ReviewQueueItem): string {
  return `${item.image}#${item.label_index ?? "none"}#${item.suspicion}`;
}

const VERDICT_TEXT: Record<Verdict, string> = { hit: "오류 맞음", miss: "오류 아님" };

function toCsv(items: ReviewQueueItem[], verdicts: Verdicts): string {
  // 좌표를 넣는 이유: 받는 쪽이 라벨링 도구다. 이미지 이름만으로는 어느
  // 박스인지 못 찾는다 — 한 장에 스무 개가 들어 있는 게 보통이다.
  const head = ["순위", "이미지", "라벨 인덱스", "의심 유형", "심각도",
                "x1", "y1", "x2", "y2", "근거", "판정"];
  const esc = (v: string | number) => {
    const s = String(v);
    // 쉼표·따옴표·줄바꿈이 들어 있으면 감싸야 한 칸으로 읽힌다
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = items.map((i) => {
    const v = verdicts[keyOf(i)];
    // 누락 의심은 가리킬 라벨이 없어 좌표도 없다. 예전 진단 결과에도 없다.
    const box = i.box ?? [];
    const coord = [0, 1, 2, 3].map((k) =>
      box[k] === undefined ? "" : box[k].toFixed(1));
    return [
      i.rank, i.image, i.label_index ?? "", i.label,
      i.severity.toFixed(3), ...coord, i.detail, v ? VERDICT_TEXT[v] : "",
    ].map(esc).join(",");
  });
  // 엑셀이 UTF-8 CSV를 한글로 열려면 BOM이 필요하다
  return "﻿" + [head.join(","), ...rows].join("\n");
}

export function ReviewQueue({ items, datasetId, fitRatio = null, robustTypes = NO_TYPES }:
                            {
                              items: ReviewQueueItem[];
                              datasetId: string;
                              /** 기준 모델이 라벨의 몇 %를 짚었나. 모르면 null. */
                              fitRatio?: number | null;
                              /** 도메인이 어긋나도 버티는 의심 유형 (docs/21 AI). */
                              robustTypes?: string[];
                            }) {
  const [type, setType] = useState("");
  const [query, setQuery] = useState("");
  const [verdicts, setVerdicts] = useState<Verdicts>(() => loadVerdicts(datasetId));
  const [onlyOpen, setOnlyOpen] = useState(false);
  // 미리보기는 이미지를 내려받으므로 기본으로 켜두면 목록이 큰 데이터셋에서
  // 수십 장을 한꺼번에 받는다. 필요할 때 켜게 한다.
  const [preview, setPreview] = useState(false);
  // 키보드로 판정할 때 "지금 어느 줄인가". -1이면 아직 아무 줄도 안 잡았다.
  const [cursor, setCursor] = useState(-1);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  const types = useMemo(() => {
    const seen = new Map<string, string>();
    items.forEach((i) => seen.set(i.suspicion, i.label));
    return [...seen.entries()];
  }, [items]);

  const shown = useMemo(() => items.filter((i) => {
    if (type && i.suspicion !== type) return false;
    if (onlyOpen && verdicts[keyOf(i)]) return false;
    if (query && !i.image.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  }), [items, type, query, verdicts, onlyOpen]);

  /** 같은 값을 다시 누르면 판정을 지운다 — 잘못 눌렀을 때 되돌릴 길이 있어야 한다. */
  const setVerdict = (item: ReviewQueueItem, v: Verdict) => {
    const k = keyOf(item);
    const next = { ...verdicts };
    if (next[k] === v) delete next[k];
    else next[k] = v;
    setVerdicts(next);
    try {
      localStorage.setItem(STORE(datasetId), JSON.stringify(next));
    } catch {
      /* 저장 못 해도 이번 세션에는 반영된다 */
    }
  };

  const download = () => {
    const blob = new Blob([toCsv(shown, verdicts)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aida_재검수목록_${datasetId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /**
   * 키보드 판정.
   *
   * j/k(또는 ↓/↑)로 줄을 옮기고 f로 "오류", d로 "아님"을 매긴다. 판정하면
   * 다음 줄로 내려간다 — 검수는 한 건씩 훑는 일이라 매번 손으로 옮기게 하면
   * 결국 안 쓴다.
   *
   * f/d를 고른 이유는 홈 포지션이어서다. 오류가 압도적으로 많으므로 오른손
   * 검지(f)에 둔다.
   *
   * 입력칸에 글자를 치는 중에는 아무것도 하지 않는다 — 이미지 이름에 'd'가
   * 들어가면 판정이 찍히는 꼴이 된다.
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (shown.length === 0) return;

      const move = (d: number) => {
        e.preventDefault();
        setCursor((c) => {
          const next = c < 0 ? (d > 0 ? 0 : shown.length - 1)
                             : Math.min(shown.length - 1, Math.max(0, c + d));
          rowRefs.current[next]?.scrollIntoView({ block: "nearest" });
          return next;
        });
      };

      if (e.key === "j" || e.key === "ArrowDown") return move(1);
      if (e.key === "k" || e.key === "ArrowUp") return move(-1);

      if (e.key === "f" || e.key === "d") {
        e.preventDefault();
        // 아무 줄도 안 잡았으면 첫 줄부터 시작한다
        const at = cursor < 0 ? 0 : cursor;
        const item = shown[at];
        if (!item) return;
        setVerdict(item, e.key === "f" ? "hit" : "miss");
        // 판정한 줄이 "안 본 것만" 때문에 사라질 수 있다. 그러면 그 자리에
        // 다음 항목이 올라오므로 커서를 그대로 두는 게 맞다.
        const next = onlyOpen ? Math.min(at, shown.length - 2) : at + 1;
        const clamped = Math.min(Math.max(next, 0), shown.length - 1);
        setCursor(clamped);
        rowRefs.current[clamped]?.scrollIntoView({ block: "nearest" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });   // 매 렌더 다시 건다 — shown/verdicts/cursor를 모두 보므로 그게 단순하다

  // 자가 이 데이터를 절반도 못 봤나. 이러면 목록 전체를 의심해야 한다.
  const shaky = fitRatio !== null && fitRatio < 0.5;
  // 그중 도메인이 어긋나도 버티는 유형이 실제로 목록에 있는가. 하나도 없으면
  // 좁힐 곳이 없다는 뜻이고, 그건 조용히 넘어갈 상황이 아니라 더 나쁜 경우다.
  const safeTypes = robustTypes.filter((t) => items.some((i) => i.suspicion === t));

  const judged = items.filter((i) => verdicts[keyOf(i)]);
  const hits = judged.filter((i) => verdicts[keyOf(i)] === "hit").length;
  const pct = items.length ? (judged.length / items.length) * 100 : 0;
  // 검수자가 실제로 확인한 것 중 몇 개가 오류였나. 우리가 KITTI에서 잰
  // 값이 아니라 이 데이터셋의 숫자다.
  const precision = judged.length ? (hits / judged.length) * 100 : null;

  return (
    <>
      <div className="queue-toolbar">
        <div className="queue-progress" title={`${judged.length} / ${items.length}`}>
          <div className="queue-progress-bar">
            <div className="queue-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="queue-progress-text">
            {judged.length} / {items.length} 판정
            {precision !== null && (
              <>
                {" · "}
                <strong>실제 오류 {precision.toFixed(0)}%</strong>
              </>
            )}
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

      <p className="queue-keys">
        키보드: <kbd>j</kbd>/<kbd>k</kbd> 줄 이동 · <kbd>f</kbd> 오류 ·{" "}
        <kbd>d</kbd> 아님 — 판정하면 다음 줄로 넘어갑니다.
      </p>

      {shaky && !type && (
        <p className="error-banner">
          기준 모델이 이 데이터의 라벨 중 {(fitRatio * 100).toFixed(0)}%밖에 짚지
          못했습니다. 도메인이 어긋나면 <b>기하 오류(크기·위치) 판정이 거의
          무너집니다</b> (docs/21 AI 실측).{" "}
          {safeTypes.length > 0 ? (
            <>
              목록은 그대로 두었으니, 버티는 유형부터 보려면 좁히세요.{" "}
              {safeTypes.map((t) => (
                <button key={t} className="verdict" onClick={() => setType(t)}>
                  {items.find((i) => i.suspicion === t)?.label ?? t}만 보기
                </button>
              ))}
            </>
          ) : (
            <>
              그런데 <b>여기서 나온 유형은 전부 그 영향을 크게 받는 것들입니다</b> —
              좁혀서 건질 것이 없다는 뜻이라 목록 전체를 의심해야 합니다. 이
              데이터에 맞는 기준 모델을 골라 다시 진단하는 편이 낫습니다.
            </>
          )}
        </p>
      )}

      {precision !== null && judged.length < items.length && (
        <p className="report-caveat">
          지금까지 판정한 {judged.length}건 기준입니다. 목록은 심각도 순이라
          위쪽이 더 맞을 가능성이 높으므로, 아래까지 내려가면 이 비율은
          떨어지는 게 정상입니다.
        </p>
      )}

      {shown.length === 0 ? (
        <p className="report-caveat">조건에 맞는 항목이 없습니다.</p>
      ) : (
        <div className="table-scroll">
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">판정</th>
                <th scope="col">#</th>
                <th scope="col">이미지</th>
                <th scope="col">라벨</th>
                <th scope="col">의심 유형</th>
                <th scope="col">근거</th>
                {preview && <th scope="col">미리보기</th>}
              </tr>
            </thead>
            <tbody>
              {shown.map((item, idx) => {
                const v = verdicts[keyOf(item)];
                const here = idx === cursor;
                return (
                  <tr key={keyOf(item)}
                      ref={(el) => { rowRefs.current[idx] = el; }}
                      onClick={() => setCursor(idx)}
                      aria-current={here ? "true" : undefined}
                      className={[v ? `row-${v}` : "", here ? "row-cursor" : ""]
                        .filter(Boolean).join(" ")}>
                    <td>
                      <div className="verdict-buttons">
                        <button
                          className={`verdict ${v === "hit" ? "verdict-on" : ""}`}
                          onClick={() => setVerdict(item, "hit")}
                          aria-pressed={v === "hit"}
                          title="실제 오류였다"
                        >
                          오류
                        </button>
                        <button
                          className={`verdict ${v === "miss" ? "verdict-on" : ""}`}
                          onClick={() => setVerdict(item, "miss")}
                          aria-pressed={v === "miss"}
                          title="라벨은 멀쩡했다"
                        >
                          아님
                        </button>
                      </div>
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
