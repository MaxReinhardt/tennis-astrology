import assert from "node:assert/strict";
import { test } from "node:test";
import { entryFor, findGlossaryTerms, lookupHeader } from "./glossary.ts";

const termsIn = (text: string) =>
  findGlossaryTerms(text).flatMap((segment) => (segment.entry ? [segment.text] : []));

test("findGlossaryTerms leaves text without jargon as one plain segment", () => {
  const segments = findGlossaryTerms("Players win matches on grass.");

  assert.deepEqual(segments, [{ text: "Players win matches on grass." }]);
});

test("findGlossaryTerms returns no segments for empty text", () => {
  assert.deepEqual(findGlossaryTerms(""), []);
});

test("findGlossaryTerms marks a known term and keeps the surrounding text", () => {
  const segments = findGlossaryTerms("The ROI was negative.");

  assert.deepEqual(
    segments.map((segment) => segment.text),
    ["The ", "ROI", " was negative."],
  );
  assert.equal(segments[1].entry?.label, "Return on investment (ROI)");
});

test("findGlossaryTerms matches regardless of case", () => {
  assert.deepEqual(termsIn("bootstrap intervals, Bootstrap again"), ["bootstrap"]);
});

test("findGlossaryTerms marks only the first occurrence of each term", () => {
  assert.deepEqual(termsIn("CLV is good. CLV is rare."), ["CLV"]);
});

test("findGlossaryTerms does not match a term inside a longer word", () => {
  assert.deepEqual(termsIn("He bankrolled the trip."), []);
});

test("findGlossaryTerms prefers the longest matching alias", () => {
  assert.deepEqual(termsIn("a 95% CI around it"), ["95% CI"]);
});

test("findGlossaryTerms joined segments reproduce the original text", () => {
  const text = "ROI and CLV with a bootstrap 95% CI on the holdout (θ = 0.02).";

  const rebuilt = findGlossaryTerms(text).map((segment) => segment.text).join("");

  assert.equal(rebuilt, text);
});

test("lookupHeader explains a table column header exactly", () => {
  assert.match(lookupHeader("p (Bonf.)")?.label ?? "", /Bonferroni/);
});

test("lookupHeader returns nothing for an unknown header", () => {
  assert.equal(lookupHeader("Surface"), undefined);
});

test("entryFor finds an entry by alias", () => {
  assert.equal(entryFor("bankroll").label, "Bankroll");
});

test("entryFor throws for an alias that is not in the glossary", () => {
  assert.throws(() => entryFor("unicorn"), /no glossary entry/);
});
