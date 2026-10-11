import type { BacktestResponse } from "@/lib/api";
import { Chart } from "./Chart";
import { InfoTip } from "./InfoTip";

export function Results({ result }: { result: BacktestResponse }) {
  return (
    <section className="space-y-4">
      <p className="text-sm text-[var(--ink-2)]">
        {result.universe.matches_seen.toLocaleString()} matches considered,{" "}
        {result.universe.bets_placed.toLocaleString()} bets placed
        {result.ruined && <strong className="ml-2 text-[var(--ink)]">⚠ bankroll ruined — sample cut short</strong>}
      </p>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {result.metrics.map((metric) => (
          <div key={metric.key} className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-3">
            <dt className="flex items-center gap-1 text-xs text-[var(--ink-3)]">
              {metric.label}
              <InfoTip title={metric.label}>{metric.description}</InfoTip>
            </dt>
            <dd className="text-lg font-semibold tabular-nums">{metric.formatted}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        {result.charts.map((chart) => (
          <Chart key={chart.key} chart={chart} />
        ))}
      </div>
    </section>
  );
}
