"use client";

import { useId, useState } from "react";

export function InfoTip({
  title,
  children,
  align = "left",
}: {
  title: string;
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const tooltipId = useId();

  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        aria-label={`What does “${title}” mean?`}
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        className="inline-flex h-3 w-3 shrink-0 items-center justify-center rounded-full border border-[var(--ink-3)] p-0 align-middle text-[8px] font-semibold leading-none text-[var(--ink-3)] hover:text-[var(--ink)]"
        onClick={() => setOpen((current) => !current)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
      >
        i
      </button>
      {open && (
        <span
          id={tooltipId}
          role="tooltip"
          className={`absolute top-full z-20 mt-1 w-64 max-w-[80vw] rounded border border-[var(--border)] bg-[var(--panel)] p-2 text-left text-xs font-normal normal-case leading-snug text-[var(--ink)] shadow-lg ${align === "right" ? "right-0" : "left-0"}`}
        >
          <strong className="block">{title}</strong>
          {children}
        </span>
      )}
    </span>
  );
}
