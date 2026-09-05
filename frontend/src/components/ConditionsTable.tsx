import { useMemo, useState } from "react";

import { typeLabel } from "../labels";
import type { ConditionMetric } from "../types";


// magnitude는 오류 유형에 따라 단위가 다르다: 회전각만 도(°), 나머지는 전부 %
function formatMagnitude(condition: ConditionMetric) {
  if (condition.type === "none") return "0";
  const sign = condition.magnitude > 0 ? "+" : "";
  const unit = condition.type === "rotation" ? "°" : "%";
  return `${sign}${condition.magnitude}${unit}`;
}

// performance_drop_pct는 "clean 대비 저하율"이라 음수면 오히려 clean보다 좋아졌다는 뜻
// (단일 시드 학습이라 발생하는 노이즈일 수 있음, docs/12-experiment-results.md 참고)
function formatDrop(value: number) {
  if (value < 0) return `+${Math.abs(value).toFixed(1)}%`;
  return `-${value.toFixed(1)}%`;
}

function formatOptionalNumber(value: number | null, digits: number) {
  return value === null ? "-" : value.toFixed(digits);
}

function formatOptionalDrop(value: number | null) {
  return value === null ? "-" : `-${value.toFixed(2)}%`;
}

// 쉼표·따옴표·줄바꿈이 든 값은 CSV 규격에 맞게 큰따옴표로 감싸야 엑셀에서 깨지지 않음
function toCsvValue(value: string | number | null) {
  const text = value === null ? "" : String(value);
  return text.includes(",") || text.includes('"') || text.includes("\n")
    ? `"${text.replace(/"/g, '""')}"`
    : text;
}

// 서버 호출 없이 이미 받아온 조건별 데이터를 그대로 CSV로 변환해 다운로드시킨다
// (백엔드에 별도 export 엔드포인트가 없어도 되는 구조, docs/14-dashboard-enhancement-plan.md 참고)
function downloadConditionsCsv(conditions: ConditionMetric[]) {
  const headers = [
    "condition",
    "type",
    "magnitude",
    "map50",
    "map50_95",
    "precision",
    "recall",
    "mean_iou",
    "mean_iou_drop_pct",
    "performance_drop_pct",
  ];
  const rows = conditions.map((condition) =>
    headers.map((key) => toCsvValue(condition[key as keyof ConditionMetric])).join(","),
  );
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const link = document.createElement("a");
  link.href = url;
  link.download = `aida_conditions_${today}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/** 열 이름과 정렬 키. 문자열 열(조건·유형)은 이름 순, 나머지는 숫자 순. */
const COLUMNS = [
  { key: "condition", label: "조건", numeric: false },
  { key: "type", label: "유형", numeric: false },
  { key: "magnitude", label: "강도", numeric: true },
  { key: "map50", label: "mAP@0.5", numeric: true },
  { key: "map50_95", label: "mAP@0.5:0.95", numeric: true },
  { key: "precision", label: "Precision", numeric: true },
  { key: "recall", label: "Recall", numeric: true },
  { key: "mean_iou", label: "평균 IoU", numeric: true },
  { key: "mean_iou_drop_pct", label: "IoU 감소율", numeric: true },
  { key: "performance_drop_pct", label: "성능 변화", numeric: true },
] as const;

type SortKey = (typeof COLUMNS)[number]["key"];

export function ConditionsTable({ conditions }: { conditions: ConditionMetric[] }) {
  // 기본은 조건 이름 순 — 지금까지 보던 순서를 바꾸지 않는다.
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>(
    { key: "condition", desc: false },
  );
  const [type, setType] = useState("");

  // 이 데이터셋에 실제로 나온 유형만 고르게 한다
  const types = useMemo(
    () => [...new Set(conditions.map((c) => c.type))].sort(),
    [conditions],
  );

  const shown = useMemo(() => {
    const col = COLUMNS.find((c) => c.key === sort.key);
    const rows = type ? conditions.filter((c) => c.type === type) : [...conditions];
    return rows.sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      // null(아직 안 잰 값)은 방향과 무관하게 항상 아래로 — 위에 몰리면
      // 정렬한 의미가 없다.
      if (x === null) return y === null ? 0 : 1;
      if (y === null) return -1;
      const d = col?.numeric
        ? Number(x) - Number(y)
        : String(x).localeCompare(String(y));
      return sort.desc ? -d : d;
    });
  }, [conditions, sort, type]);

  const clickSort = (key: SortKey) =>
    setSort((s) => (s.key === key
      // 같은 열을 또 누르면 방향만 뒤집는다
      ? { key, desc: !s.desc }
      // 새 열은 숫자면 큰 값부터. "제일 많이 떨어진 것"을 찾는 게 보통이다.
      : { key, desc: !!COLUMNS.find((c) => c.key === key)?.numeric }));

  return (
    <section className="card">
      <div className="card-heading-row">
        <h2>조건별 상세 지표</h2>
        <div className="queue-controls">
          <label className="sr-only" htmlFor="cond-type">오류 유형으로 좁히기</label>
          <select id="cond-type" className="profile-select" value={type}
                  onChange={(e) => setType(e.target.value)}>
            <option value="">유형 전체 ({conditions.length})</option>
            {types.map((t) => (
              <option key={t} value={t}>{typeLabel(t)}</option>
            ))}
          </select>
          <button
            className="refresh-button"
            type="button"
            onClick={() => downloadConditionsCsv(shown)}
            disabled={shown.length === 0}
          >
            CSV 다운로드
          </button>
        </div>
      </div>

      <p className="report-caveat">
        열 제목을 누르면 그 값으로 정렬합니다. CSV는 지금 보이는 것만 받습니다.
      </p>

      <div className="table-scroll">
        <table className="report-table metrics-table">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col"
                    aria-sort={sort.key === c.key
                      ? (sort.desc ? "descending" : "ascending")
                      : "none"}>
                  <button type="button" className="sort-header"
                          onClick={() => clickSort(c.key)}>
                    {c.label}
                    <span className="sort-arrow" aria-hidden="true">
                      {sort.key === c.key ? (sort.desc ? "▼" : "▲") : "\u00a0"}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((condition) => (
              <tr key={condition.condition}>
                <td>{condition.condition}</td>
                <td>{typeLabel(condition.type)}</td>
                <td>{formatMagnitude(condition)}</td>
                <td>{condition.map50.toFixed(3)}</td>
                <td>{condition.map50_95.toFixed(3)}</td>
                <td>{condition.precision.toFixed(3)}</td>
                <td>{condition.recall.toFixed(3)}</td>
                <td>{formatOptionalNumber(condition.mean_iou, 4)}</td>
                <td>{formatOptionalDrop(condition.mean_iou_drop_pct)}</td>
                <td>{formatDrop(condition.performance_drop_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
