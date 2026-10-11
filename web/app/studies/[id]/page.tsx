"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Chart } from "@/components/Chart";
import { GlossaryHeader, GlossaryText } from "@/components/GlossaryText";
import { VerdictBadge } from "@/components/VerdictBadge";
import { api, type Study } from "@/lib/api";

const HYPOTHESIS_LABELS: [string, string][] = [
  ["rationale", "Why it might work"],
  ["metric", "What is measured"],
  ["threshold", "How it is judged"],
  ["in_sample", "Older seasons (tuning allowed)"],
  ["out_of_sample", "Unseen seasons (looked at once)"],
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
          <h1 className="text-xl font-semibold">{study.plain_title}</h1>
          <VerdictBadge verdict={study.verdict} />
        </div>
        <p className="text-xs text-[var(--ink-3)]">{study.title}</p>
        <p className="text-sm"><GlossaryText text={study.plain_summary} /></p>
        <p className="text-sm"><strong>Result:</strong> <GlossaryText text={study.conclusion} /></p>
      </header>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">The exact hypothesis, as written before the results</h2>
        <p className="text-sm"><GlossaryText text={study.hypothesis.statement} /></p>
        <dl className="space-y-1 text-sm">
          {HYPOTHESIS_LABELS.map(([key, label]) => (
            <div key={key}>
              <dt className="inline text-[var(--ink-3)]">{label}: </dt>
              <dd className="inline"><GlossaryText text={study.hypothesis[key]} /></dd>
            </div>
          ))}
        </dl>
      </section>

      {study.tables.map((table) => (
        <section key={table.title} className="space-y-2">
          <h2 className="text-sm font-semibold"><GlossaryText text={table.title} /></h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--ink-3)]">
                  {table.columns.map((column) => <th key={column} className="py-1 pr-4 font-medium"><GlossaryHeader text={column} /></th>)}
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
