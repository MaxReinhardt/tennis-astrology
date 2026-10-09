"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartPoint, ChartSeries } from "@/lib/api";

const PERCENT_AXES = new Set([
  "ROI", "Drawdown", "CLV", "Realised win rate", "Share of bets", "Win-rate gap",
]);

const percent = (value: number) => `${(value * 100).toFixed(Math.abs(value) < 0.1 ? 1 : 0)}%`;
const label = (value: number | string) => (typeof value === "number" ? percent(value) : value);

function axisFormatter(name: string) {
  return PERCENT_AXES.has(name) ? percent : (value: number) => String(value);
}

const axisProps = {
  stroke: "var(--ink-3)",
  tick: { fill: "var(--ink-2)", fontSize: 12 },
  tickLine: false,
} as const;

const tooltipProps = {
  contentStyle: {
    background: "var(--panel)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    color: "var(--ink)",
    fontSize: 12,
  },
  labelStyle: { color: "var(--ink-2)" },
} as const;

type TickProps = { x?: number; y?: number; payload?: { value: string } };

function MultilineTick({ x = 0, y = 0, payload }: TickProps) {
  const lines = String(payload?.value ?? "").split("\n");
  return (
    <text x={x} y={y} textAnchor="middle" fill="var(--ink-2)" fontSize={12}>
      {lines.map((line, index) => (
        <tspan key={index} x={x} dy={14}>{line}</tspan>
      ))}
    </text>
  );
}

function withError(points: ChartPoint[]) {
  return points.map((point) => ({
    ...point,
    tick: point.count === undefined ? String(point.x) : `${point.x}\nn=${point.count.toLocaleString()}`,
    err: point.low === undefined || point.high === undefined ? undefined : [point.y - point.low, point.high - point.y],
  }));
}

function Plot({ chart }: { chart: ChartSeries }) {
  const formatY = axisFormatter(chart.y_label);
  const grid = <CartesianGrid vertical={false} stroke="var(--border)" />;

  if (chart.kind === "line") {
    return (
      <LineChart data={chart.points} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
        {grid}
        <XAxis dataKey="x" {...axisProps} minTickGap={48} />
        <YAxis {...axisProps} tickFormatter={formatY} width={64} domain={["auto", "auto"]} />
        <Tooltip {...tooltipProps} formatter={(v) => [formatY(Number(v)), chart.y_label]} />
        <Line dataKey="y" stroke="var(--series)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    );
  }

  if (chart.kind === "calibration") {
    return (
      <LineChart data={chart.points} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
        {grid}
        <XAxis dataKey="x" type="number" domain={[0, 1]} {...axisProps} tickFormatter={percent} />
        <YAxis type="number" domain={[0, 1]} {...axisProps} tickFormatter={percent} width={48} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="var(--reference)" strokeDasharray="4 4" />
        <Tooltip {...tooltipProps} formatter={(v) => [percent(Number(v)), "Realised"]} labelFormatter={(v) => `Predicted ${label(Number(v))}`} />
        <Line dataKey="y" stroke="var(--series)" strokeWidth={2} dot={{ r: 4, fill: "var(--series)", stroke: "var(--panel)", strokeWidth: 2 }} isAnimationActive={false} />
      </LineChart>
    );
  }

  const data = chart.kind === "bar" ? withError(chart.points) : chart.points;
  return (
    <BarChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }} barCategoryGap={chart.kind === "histogram" ? 1 : "30%"}>
      {grid}
      <XAxis
        dataKey={chart.kind === "bar" ? "tick" : "x"}
        {...axisProps}
        tick={chart.kind === "bar" ? <MultilineTick /> : axisProps.tick}
        tickFormatter={chart.kind === "histogram" ? (v) => percent(Number(v)) : undefined}
        interval={0}
        height={chart.kind === "bar" ? 44 : 30}
      />
      <YAxis {...axisProps} tickFormatter={formatY} width={64} />
      <ReferenceLine y={0} stroke="var(--reference)" />
      <Tooltip
        {...tooltipProps}
        cursor={{ fill: "var(--border)", opacity: 0.4 }}
        formatter={(v) => [formatY(Number(v)), chart.y_label]}
      />
      <Bar dataKey="y" fill="var(--series)" radius={[4, 4, 0, 0]} isAnimationActive={false}>
        {chart.kind === "bar" && <ErrorBar dataKey="err" stroke="var(--ink-2)" strokeWidth={1.5} width={6} isAnimationActive={false} />}
      </Bar>
    </BarChart>
  );
}

export function Chart({ chart }: { chart: ChartSeries }) {
  const formatY = axisFormatter(chart.y_label);
  const formatX = (point: ChartPoint) => (typeof point.x === "number" && chart.kind !== "line" ? percent(point.x) : String(point.x));

  return (
    <figure className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4">
      <figcaption className="mb-2 text-sm font-medium">{chart.title}</figcaption>
      {chart.points.length === 0 ? (
        <p className="py-10 text-center text-sm text-[var(--ink-3)]">No data</p>
      ) : (
        <div role="img" aria-label={`${chart.title}: ${chart.y_label} by ${chart.x_label}`} className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <Plot chart={chart} />
          </ResponsiveContainer>
        </div>
      )}
      {chart.points.length > 0 && chart.points.length <= 40 && (
        <details className="mt-2 text-xs text-[var(--ink-2)]">
          <summary className="cursor-pointer">Table view</summary>
          <table className="mt-2 w-full">
            <thead>
              <tr className="text-left text-[var(--ink-3)]">
                <th>{chart.x_label}</th><th>{chart.y_label}</th><th>Interval</th><th>n</th>
              </tr>
            </thead>
            <tbody>
              {chart.points.map((point, index) => (
                <tr key={index}>
                  <td>{formatX(point)}</td>
                  <td>{formatY(point.y)}</td>
                  <td>{point.low === undefined ? "" : `${formatY(point.low)} … ${formatY(point.high ?? 0)}`}</td>
                  <td>{point.count ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </figure>
  );
}
