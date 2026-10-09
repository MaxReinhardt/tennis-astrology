"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Chart } from "@/components/Chart";
import { VerdictBadge } from "@/components/VerdictBadge";
import { api, type Study } from "@/lib/api";

const HYPOTHESIS_LABELS: [string, string][] = [
  ["rationale", "Economic rationale"],
  ["metric", "Pre-registered metric"],
  ["threshold", "Decision rule"],
  ["in_sample", "In-sample (tuning allowed)"],
  ["out_of_sample", "Out-of-sample (touched once)"],
];

export default function StudyPage() {
  const { id } = useParams<{ id: string }>();
  const [study, setStudy] = useState<Study | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.study(id).then(setStudy).catch((cause: Error) => setError(cause.message));
  }, [id]);

  if (error) return <p role="alert" className="text-sm">⚠ {error}</p>;
  if (!study) return <p className="text-sm text-[var(--ink-2)]">Loading…</p>;

  return (
    <article className="space-y-6">
      <Link href="/studies" className="text-sm text-[var(--ink-2)] hover:underline">← All studies</Link>
      <header className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-xl font-semibold">{study.title}</h1>
          <VerdictBadge verdict={study.verdict} />
        </div>
        <p className="text-sm">{study.conclusion}</p>
      </header>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Hypothesis</h2>
        <p className="text-sm">{study.hypothesis.statement}</p>
        <dl className="space-y-1 text-sm">
          {HYPOTHESIS_LABELS.map(([key, label]) => (
            <div key={key}>
              <dt className="inline text-[var(--ink-3)]">{label}: </dt>
              <dd className="inline">{study.hypothesis[key]}</dd>
            </div>
          ))}
        </dl>
      </section>

      {study.tables.map((table) => (
        <section key={table.title} className="space-y-2">
          <h2 className="text-sm font-semibold">{table.title}</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--ink-3)]">
                  {table.columns.map((column) => <th key={column} className="py-1 pr-4 font-medium">{column}</th>)}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, index) => (
                  <tr key={index} className="border-b border-[var(--border)]">
                    {row.map((cell, cellIndex) => <td key={cellIndex} className="py-1 pr-4">{cell}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <section className="grid gap-4 lg:grid-cols-2">
        {study.charts.map((chart) => <Chart key={chart.key} chart={chart} />)}
      </section>
    </article>
  );
}
