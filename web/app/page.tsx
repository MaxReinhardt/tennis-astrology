"use client";

import { useEffect, useState } from "react";
import { RequestForm, emptyRequest } from "@/components/RequestForm";
import { Results } from "@/components/Results";
import { api, type BacktestRequest, type BacktestResponse, type Catalog, type Health } from "@/lib/api";

const EXAMPLES = [
  "Do clay-court underdogs beat the market since 2015?",
  "Does backing home-nation players make money?",
  "Does Elo disagreeing with the market by 8% pay off on grass?",
];

export default function AskPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [request, setRequest] = useState<BacktestRequest | null>(null);
  const [question, setQuestion] = useState("");
  const [interpretation, setInterpretation] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"translate" | "run" | null>(null);

  useEffect(() => {
    Promise.all([api.catalog(), api.health()])
      .then(([loadedCatalog, loadedHealth]) => {
        setCatalog(loadedCatalog);
        setHealth(loadedHealth);
        setRequest(emptyRequest(loadedCatalog));
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  async function guarded<T>(kind: "translate" | "run", action: () => Promise<T>) {
    setBusy(kind);
    setError(null);
    try {
      return await action();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const translate = (text: string) =>
    guarded("translate", async () => {
      const translation = await api.translate(text);
      setInterpretation(translation.interpretation);
      setRequest(translation.request);
      setResult(null);
    });

  const run = () =>
    guarded("run", async () => {
      setResult(await api.backtest(request));
    });

  if (!catalog || !request) {
    return <p className="text-sm text-[var(--ink-2)]">{error ?? "Loading…"}</p>;
  }

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h1 className="text-xl font-semibold">Ask a question</h1>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            void translate(question);
          }}
        >
          <input
            className="flex-1 rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={health?.translation_enabled ? "e.g. " + EXAMPLES[0] : "Questions are disabled — set the controls below"}
            disabled={!health?.translation_enabled}
            aria-label="Question"
          />
          <button
            className="rounded bg-[var(--series)] px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            disabled={!health?.translation_enabled || !question.trim() || busy !== null}
          >
            {busy === "translate" ? "Interpreting…" : "Interpret"}
          </button>
        </form>
        {health?.translation_enabled && (
          <div className="flex flex-wrap gap-2 text-xs">
            {EXAMPLES.map((example) => (
              <button key={example} className="rounded-full border border-[var(--border)] px-3 py-1 text-[var(--ink-2)] hover:text-[var(--ink)]" onClick={() => { setQuestion(example); void translate(example); }}>
                {example}
              </button>
            ))}
          </div>
        )}
        {interpretation && (
          <p className="rounded border border-[var(--border)] bg-[var(--panel)] p-3 text-sm">
            <strong>Interpreted as:</strong> {interpretation}
          </p>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Backtest settings</h2>
        <RequestForm catalog={catalog} value={request} onChange={setRequest} />
        <button className="rounded bg-[var(--series)] px-4 py-2 text-sm font-medium text-white disabled:opacity-40" onClick={() => void run()} disabled={busy !== null}>
          {busy === "run" ? "Running…" : "Run backtest"}
        </button>
        <p className="text-xs text-[var(--ink-3)]">
          Data source: {health?.source}. Odds are closing prices; results are in-sample unless you restrict the seasons — see the Studies for the pre-registered protocol.
        </p>
      </section>

      {error && <p role="alert" className="rounded border border-[var(--border)] bg-[var(--panel)] p-3 text-sm">⚠ {error}</p>}
      {result && <Results result={result} />}
    </div>
  );
}
