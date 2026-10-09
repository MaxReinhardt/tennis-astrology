"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { VerdictBadge } from "@/components/VerdictBadge";
import { api, type StudySummary } from "@/lib/api";

export default function StudiesPage() {
  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.studies().then(setStudies).catch((cause: Error) => setError(cause.message));
  }, []);

  if (error) return <p role="alert" className="text-sm">⚠ {error}</p>;
  if (!studies) return <p className="text-sm text-[var(--ink-2)]">Loading…</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Studies</h1>
      <p className="text-sm text-[var(--ink-2)]">
        Each study states its hypothesis and decision rule before looking at results, tunes only on
        seasons up to 2018, and is judged on 2019 onward.
      </p>
      <ul className="space-y-3">
        {studies.map((study) => (
          <li key={study.study_id} className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4">
            <div className="flex items-start justify-between gap-3">
              <Link href={`/studies/${study.study_id}`} className="font-medium hover:underline">{study.title}</Link>
              <VerdictBadge verdict={study.verdict} />
            </div>
            <p className="mt-1 text-sm text-[var(--ink-2)]">{study.statement}</p>
            <p className="mt-2 text-sm">{study.conclusion}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
