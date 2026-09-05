import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { typeLabel } from "../labels";
import type { ConditionMetric, ConditionMetricAgg } from "../types";


function label(c: { type: string; magnitude: number }) {
  return `${typeLabel(c.type)}${c.magnitude !== 0 ? ` ${c.magnitude > 0 ? "+" : ""}${c.magnitude}` : ""}`;
}

// 기본값 배열을 인자 자리에 두면 렌더마다 새 배열이 만들어져 참조가 달라진다.
// 밖에 한 번 만들어 두고 쓴다.
const NO_AGGREGATE: ConditionMetricAgg[] = [];

export function PerformanceChart({
  conditions,
  aggregated = NO_AGGREGATE,
}: {
  conditions: ConditionMetric[];
  aggregated?: ConditionMetricAgg[];
}) {
  const hasAgg = aggregated.length > 0;

  const data = hasAgg
    ? aggregated.map((c) => ({
        name: label(c),
        drop: c.drop_pct_mean ?? 0,
        errorVal: c.drop_pct_std != null ? [c.drop_pct_std, c.drop_pct_std] : undefined,
        nSeeds: c.n_seeds,
      }))
    : conditions.map((c) => ({
        name: label(c),
        drop: c.performance_drop_pct,
        errorVal: undefined,
        nSeeds: 1,
      }));

  return (
    <section className="card">
      <h2>
        오류 조건별 성능 저하 (mAP@0.5 기준)
        {hasAgg && (
          <span style={{ fontSize: "0.75rem", fontWeight: "normal", color: "#595959", marginLeft: "0.75rem" }}>
            {aggregated[0]?.n_seeds}개 seed 평균 ± 표준편차
          </span>
        )}
      </h2>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="#E0E0E0" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "#595959" }}
            interval={0}
            angle={-15}
            textAnchor="end"
            height={60}
          />
          <YAxis tick={{ fontSize: 11, fill: "#595959" }} unit="%" />
          <Tooltip
            formatter={(v, _name, props) => {
              const std = props.payload?.errorVal?.[0];
              return std != null
                ? [`-${v}% ± ${std}%`, "성능 저하"]
                : [`-${v}%`, "성능 저하"];
            }}
          />
          <Bar dataKey="drop" fill="#000000" radius={[2, 2, 0, 0]}>
            {hasAgg && (
              <ErrorBar dataKey="errorVal" width={4} strokeWidth={2} stroke="#CCFF00" direction="y" />
            )}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
