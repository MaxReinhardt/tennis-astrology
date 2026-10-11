import { findGlossaryTerms, lookupHeader } from "@/lib/glossary";
import { InfoTip } from "./InfoTip";

export function GlossaryText({ text }: { text: string }) {
  return (
    <>
      {findGlossaryTerms(text).map((segment, index) =>
        segment.entry ? (
          <span key={index} className="whitespace-nowrap">
            <span className="underline decoration-dotted underline-offset-2">{segment.text}</span>{" "}
            <InfoTip title={segment.entry.label}>{segment.entry.explanation}</InfoTip>
          </span>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

export function GlossaryHeader({ text }: { text: string }) {
  const entry = lookupHeader(text);
  if (!entry) return <GlossaryText text={text} />;
  return (
    <span className="inline-flex items-center gap-1">
      {text}
      <InfoTip title={entry.label}>{entry.explanation}</InfoTip>
    </span>
  );
}
