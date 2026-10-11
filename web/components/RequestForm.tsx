"use client";

import { useId } from "react";
import type { BacktestRequest, Catalog, Definition, ParameterSpec } from "@/lib/api";
import { entryFor } from "@/lib/glossary";
import { InfoTip } from "./InfoTip";

const SURFACES = ["Hard", "Clay", "Grass", "Carpet"];
const field = "rounded border border-[var(--border)] bg-[var(--panel)] px-2 py-1 text-sm";

function Field({
  label,
  help,
  helpTitle,
  className = "",
  align,
  children,
}: {
  label: string;
  help: string;
  helpTitle?: string;
  className?: string;
  align?: "left" | "right";
  children: (id: string) => React.ReactNode;
}) {
  const id = useId();
  return (
    <div className={`flex flex-col gap-1 text-xs text-[var(--ink-2)] ${className}`}>
      <span className="flex items-center gap-1">
        <label htmlFor={id}>{label}</label>
        <InfoTip title={helpTitle ?? label} align={align}>{help}</InfoTip>
      </span>
      {children(id)}
    </div>
  );
}

function GlossaryField({ term, label, ...rest }: { term: string; label: string; className?: string; align?: "left" | "right"; children: (id: string) => React.ReactNode }) {
  const entry = entryFor(term);
  return <Field label={label} help={entry.explanation} helpTitle={entry.label} {...rest} />;
}

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
        <Field key={spec.name} label={spec.label} help={spec.description}>
          {(id) => (
            <input
              id={id}
              type="number"
              className={field}
              value={values[spec.name] ?? spec.default}
              min={spec.minimum ?? undefined}
              max={spec.maximum ?? undefined}
              step={spec.type === "integer" ? 1 : "any"}
              onChange={(event) => onChange({ ...values, [spec.name]: Number(event.target.value) })}
            />
          )}
        </Field>
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
    <Field
      label={key === "from_season" ? "From season" : "To season"}
      help="A season is a calendar year of matches. Leave empty for no limit. Odds data starts in 2001 for men (ATP) and 2007 for women (WTA)."
      helpTitle="Season"
    >
      {(id) => (
        <input
          id={id}
          type="number"
          className={field}
          value={value.filters[key] ?? ""}
          placeholder="any"
          onChange={(event) => setFilters({ [key]: event.target.value === "" ? null : Number(event.target.value) })}
        />
      )}
    </Field>
  );

  const changeStrategy = (name: string) =>
    onChange({
      ...value,
      strategy: name,
      strategy_parameters: defaultsFor(catalog.strategies.find((item) => item.name === name)),
    });
  const changeStakeRule = (name: string) =>
    onChange({
      ...value,
      stake_rule: name,
      stake_parameters: defaultsFor(catalog.stake_rules.find((item) => item.name === name)),
    });
  const toggleSurface = (surface: string, checked: boolean) =>
    setFilters({
      surfaces: checked ? [...value.filters.surfaces, surface] : value.filters.surfaces.filter((item) => item !== surface),
    });

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <GlossaryField term="strategy" label="Betting rule (strategy)" className="sm:col-span-2">
        {(id) => (
          <>
            <select id={id} className={field} value={value.strategy} onChange={(event) => changeStrategy(event.target.value)}>
              {catalog.strategies.map((item) => (
                <option key={item.name} value={item.name}>{item.label}</option>
              ))}
            </select>
            <span className="text-[var(--ink-3)]">{strategy?.description}</span>
          </>
        )}
      </GlossaryField>
      <ParameterInputs
        specs={strategy?.parameters ?? []}
        values={value.strategy_parameters}
        onChange={(next) => onChange({ ...value, strategy_parameters: next })}
      />

      <Field label="Tour" help="ATP is the men's professional tour and WTA is the women's. Choose both to include every match." helpTitle="Tour">
        {(id) => (
          <select id={id} className={field} value={value.filters.tour ?? ""} onChange={(event) => setFilters({ tour: event.target.value || null })}>
            <option value="">ATP + WTA</option>
            <option value="atp">ATP (men)</option>
            <option value="wta">WTA (women)</option>
          </select>
        )}
      </Field>
      {seasonInput("from_season")}
      {seasonInput("to_season")}
      <fieldset className="flex flex-col gap-1 text-xs text-[var(--ink-2)]">
        <legend className="flex items-center gap-1">
          Court surface (none = all)
          <InfoTip title="Court surface" align="right">
            Hard, clay, grass and carpet courts play differently, and some players do much better on one of them.
          </InfoTip>
        </legend>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {SURFACES.map((surface) => (
            <label key={surface} className="flex items-center gap-1">
              <input type="checkbox" checked={value.filters.surfaces.includes(surface)} onChange={(event) => toggleSurface(surface, event.target.checked)} />
              {surface}
            </label>
          ))}
        </div>
      </fieldset>

      <GlossaryField term="staking" label="Bet size (staking)">
        {(id) => (
          <select id={id} className={field} value={value.stake_rule} onChange={(event) => changeStakeRule(event.target.value)}>
            {catalog.stake_rules.map((item) => (
              <option key={item.name} value={item.name}>{item.label}</option>
            ))}
          </select>
        )}
      </GlossaryField>
      <ParameterInputs
        specs={stake?.parameters ?? []}
        values={value.stake_parameters}
        onChange={(next) => onChange({ ...value, stake_parameters: next })}
      />
      <GlossaryField term="slippage" label="Price penalty (slippage)">
        {(id) => (
          <input id={id} type="number" step="any" min={0} max={1} className={field} value={value.slippage} onChange={(event) => onChange({ ...value, slippage: Number(event.target.value) })} />
        )}
      </GlossaryField>
      <GlossaryField term="bankroll" label="Starting money (bankroll)" align="right">
        {(id) => (
          <input id={id} type="number" min={1} className={field} value={value.starting_bankroll} onChange={(event) => onChange({ ...value, starting_bankroll: Number(event.target.value) })} />
        )}
      </GlossaryField>
    </div>
  );
}
