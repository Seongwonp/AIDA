import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ConditionMetric } from "../types";

const TYPE_LABELS: Record<string, string> = {
  none: "기준선",
  width: "가로 오류",
  height: "세로 오류",
  rotation: "회전각 오류",
  translation_x: "가로이동 오류",
  translation_y: "세로이동 오류",
  scale: "스케일 오류",
};

export function PerformanceChart({ conditions }: { conditions: ConditionMetric[] }) {
  const data = conditions.map((c) => ({
    name: `${TYPE_LABELS[c.type] ?? c.type}${c.magnitude !== 0 ? ` ${c.magnitude > 0 ? "+" : ""}${c.magnitude}` : ""}`,
    drop: c.performance_drop_pct,
  }));

  return (
    <section className="card">
      <h2>오류 조건별 성능 저하 (mAP@0.5 기준)</h2>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="#E0E0E0" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#595959" }} interval={0} angle={-15} textAnchor="end" height={60} />
          <YAxis tick={{ fontSize: 11, fill: "#595959" }} unit="%" />
          <Tooltip formatter={(v) => [`-${v}%`, "성능 저하"]} />
          <Bar dataKey="drop" fill="#000000" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
