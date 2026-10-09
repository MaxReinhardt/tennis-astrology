"use client";

import type { BacktestRequest, Catalog, Definition, ParameterSpec } from "@/lib/api";

const SURFACES = ["Hard", "Clay", "Grass", "Carpet"];
const field = "rounded border border-[var(--border)] bg-[var(--panel)] px-2 py-1 text-sm";
const labelClass = "flex flex-col gap-1 text-xs text-[var(--ink-2)]";

export const defaultsFor = (definition: Definition | undefined) =>
  Object.fromEntries((definition?.parameters ?? []).map((spec) => [spec.name, spec.default]));

export function emptyRequest(catalog: Catalog): BacktestRequest {
  const strategy = catalog.strategies[0];
  const stake = catalog.stake_rules.find((rule) => rule.name === "flat") ?? catalog.stake_rules[0];
  return {
    strategy: strategy.name,
    strategy_parameters: defaultsFor(strategy),
    filters: { tour: null, surfaces: [], from_season: null, to_season: null },
    stake_rule: stake.name,
    stake_parameters: { ...defaultsFor(stake), amount: 10 },
    slippage: 0.01,
    starting_bankroll: 1_000_000,
  };
}

function ParameterInputs({
  specs,
  values,
  onChange,
}: {
  specs: ParameterSpec[];
  values: Record<string, number>;
  onChange: (next: Record<string, number>) => void;
}) {
  return (
    <>
      {specs.map((spec) => (
        <label key={spec.name} className={labelClass} title={spec.description}>
          {spec.name}
          <input
            type="number"
            className={field}
            value={values[spec.name] ?? spec.default}
            min={spec.minimum ?? undefined}
            max={spec.maximum ?? undefined}
            step={spec.type === "integer" ? 1 : "any"}
            onChange={(event) => onChange({ ...values, [spec.name]: Number(event.target.value) })}
          />
        </label>
      ))}
    </>
  );
}

export function RequestForm({
  catalog,
  value,
  onChange,
}: {
  catalog: Catalog;
  value: BacktestRequest;
  onChange: (next: BacktestRequest) => void;
}) {
  const strategy = catalog.strategies.find((item) => item.name === value.strategy);
  const stake = catalog.stake_rules.find((item) => item.name === value.stake_rule);
  const setFilters = (patch: Partial<BacktestRequest["filters"]>) =>
    onChange({ ...value, filters: { ...value.filters, ...patch } });
  const seasonInput = (key: "from_season" | "to_season") => (
    <label className={labelClass}>
      {key === "from_season" ? "From season" : "To season"}
      <input
        type="number"
        className={field}
        value={value.filters[key] ?? ""}
        placeholder="any"
        onChange={(event) => setFilters({ [key]: event.target.value === "" ? null : Number(event.target.value) })}
      />
    </label>
  );

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <label className={`${labelClass} sm:col-span-2`}>
        Strategy
        <select
          className={field}
          value={value.strategy}
          onChange={(event) =>
            onChange({
              ...value,
              strategy: event.target.value,
              strategy_parameters: defaultsFor(catalog.strategies.find((s) => s.name === event.target.value)),
            })
          }
        >
          {catalog.strategies.map((item) => (
            <option key={item.name} value={item.name}>{item.name}</option>
          ))}
        </select>
        <span className="text-[var(--ink-3)]">{strategy?.description}</span>
      </label>
      <ParameterInputs
        specs={strategy?.parameters ?? []}
        values={value.strategy_parameters}
        onChange={(next) => onChange({ ...value, strategy_parameters: next })}
      />

      <label className={labelClass}>
        Tour
        <select className={field} value={value.filters.tour ?? ""} onChange={(event) => setFilters({ tour: event.target.value || null })}>
          <option value="">ATP + WTA</option>
          <option value="atp">ATP</option>
          <option value="wta">WTA</option>
        </select>
      </label>
      {seasonInput("from_season")}
      {seasonInput("to_season")}
      <fieldset className="flex flex-col gap-1 text-xs text-[var(--ink-2)]">
        <legend>Surfaces (none = all)</legend>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {SURFACES.map((surface) => (
            <label key={surface} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={value.filters.surfaces.includes(surface)}
                onChange={(event) =>
                  setFilters({
                    surfaces: event.target.checked
                      ? [...value.filters.surfaces, surface]
                      : value.filters.surfaces.filter((s) => s !== surface),
                  })
                }
              />
              {surface}
            </label>
          ))}
        </div>
      </fieldset>

      <label className={labelClass}>
        Staking
        <select
          className={field}
          value={value.stake_rule}
          onChange={(event) =>
            onChange({
              ...value,
              stake_rule: event.target.value,
              stake_parameters: defaultsFor(catalog.stake_rules.find((r) => r.name === event.target.value)),
            })
          }
        >
          {catalog.stake_rules.map((item) => (
            <option key={item.name} value={item.name}>{item.name}</option>
          ))}
        </select>
      </label>
      <ParameterInputs
        specs={stake?.parameters ?? []}
        values={value.stake_parameters}
        onChange={(next) => onChange({ ...value, stake_parameters: next })}
      />
      <label className={labelClass}>
        Slippage
        <input type="number" step="any" min={0} max={1} className={field} value={value.slippage} onChange={(event) => onChange({ ...value, slippage: Number(event.target.value) })} />
      </label>
      <label className={labelClass}>
        Starting bankroll
        <input type="number" min={1} className={field} value={value.starting_bankroll} onChange={(event) => onChange({ ...value, starting_bankroll: Number(event.target.value) })} />
      </label>
    </div>
  );
}
