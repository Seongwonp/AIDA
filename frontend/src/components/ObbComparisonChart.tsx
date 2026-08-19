import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ConditionMetric } from "../types";

// AABB와 OBB의 회전 조건을 magnitude 기준으로 대응시켜 나란히 비교한다.
const ROT_MAGNITUDES = [-15, -7.5, 7.5, 15];

interface ComparisonRow {
  label: string;
  aabb: number | null;
  obb: number | null;
}

function buildComparisonData(
  aabbConditions: ConditionMetric[],
  obbConditions: ConditionMetric[]
): ComparisonRow[] {
  const aabbByMag = new Map(
    aabbConditions
      .filter((c) => c.type === "rotation")
      .map((c) => [c.magnitude, c.performance_drop_pct])
  );
  const obbByMag = new Map(
    obbConditions
      .filter((c) => c.type === "rotation")
      .map((c) => [c.magnitude, c.performance_drop_pct])
  );

  return ROT_MAGNITUDES.map((mag) => ({
    label: `${mag > 0 ? "+" : ""}${mag}°`,
    aabb: aabbByMag.get(mag) ?? null,
    obb: obbByMag.get(mag) ?? null,
  }));
}

export function ObbComparisonChart({
  aabbConditions,
  obbConditions,
}: {
  aabbConditions: ConditionMetric[];
  obbConditions: ConditionMetric[];
}) {
  if (obbConditions.length === 0) {
    return (
      <section className="card">
        <h2>OBB vs AABB 회전 오류 비교</h2>
        <p style={{ color: "#888", fontSize: "0.9rem", marginTop: "0.5rem" }}>
          OBB 실험 결과 없음 —{" "}
          <code>python run_obb.py</code> 실행 후 새로고침하면 표시됩니다.
        </p>
      </section>
    );
  }

  const data = buildComparisonData(aabbConditions, obbConditions);

  return (
    <section className="card">
      <h2>OBB vs AABB 회전 오류 비교</h2>
      <p style={{ color: "#595959", fontSize: "0.85rem", marginBottom: "1rem" }}>
        AABB: 회전 후 축정렬 외접 박스 → 방향성 소실 (±θ 저하율 유사)
        <br />
        OBB: 회전된 polygon 그대로 → 방향성 보존 (+θ / −θ 저하율 차별화)
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="#E0E0E0" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#595959" }} />
          <YAxis tick={{ fontSize: 11, fill: "#595959" }} unit="%" />
          <Tooltip formatter={(v, name) => [`-${v}%`, name === "aabb" ? "AABB" : "OBB"]} />
          <Legend formatter={(v) => (v === "aabb" ? "AABB (현재)" : "OBB (신규)")} />
          <Bar dataKey="aabb" fill="#BBBBBB" radius={[2, 2, 0, 0]} />
          <Bar dataKey="obb" fill="#000000" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
