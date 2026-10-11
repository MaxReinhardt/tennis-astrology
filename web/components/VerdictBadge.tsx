import type { Verdict } from "@/lib/api";

const LABELS: Record<Verdict, string> = {
  supported: "✓ Supported",
  not_supported: "✕ Not supported",
  inconclusive: "? Inconclusive",
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs font-medium">
      {LABELS[verdict]}
    </span>
  );
}
