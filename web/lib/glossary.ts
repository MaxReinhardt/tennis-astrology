export type GlossaryEntry = {
  label: string;
  explanation: string;
  aliases: string[];
  headers?: string[];
};

export type GlossarySegment = { text: string; entry?: GlossaryEntry };

export const GLOSSARY: GlossaryEntry[] = [
  {
    label: "Strategy",
    explanation: "The rule that decides which player to bet on in each match.",
    aliases: ["strategy", "strategies"],
  },
  {
    label: "Staking (bet size)",
    explanation: "How much money is risked on each bet. It can be the same every time or depend on how confident we are.",
    aliases: ["staking", "stake"],
  },
  {
    label: "Slippage",
    explanation: "A price penalty. Quoted odds can move or vanish before a bet is placed, so we assume slightly worse odds than the ones we saw. 1% is a cautious default.",
    aliases: ["slippage"],
  },
  {
    label: "Bankroll",
    explanation: "The pot of money the simulation starts with. Bets are paid from it, winnings are added to it, and it can run out.",
    aliases: ["bankroll"],
  },
  {
    label: "Odds (price)",
    explanation: "Decimal odds: 2.00 doubles your stake if you win, 1.50 returns half again, 5.00 returns five times. Higher odds mean the bookmaker thinks the player is less likely to win.",
    aliases: ["odds", "price", "prices"],
  },
  {
    label: "Favourite / underdog",
    explanation: "The favourite is the player the bookmaker thinks is more likely to win (lower odds). The underdog is the other one.",
    aliases: ["favourites", "favourite", "underdogs", "underdog"],
  },
  {
    label: "Long shot",
    explanation: "A player with high odds, which means the bookmaker thinks a win is unlikely but the payout is large.",
    aliases: ["longshots", "longshot", "long shots", "long shot"],
  },
  {
    label: "Tour",
    explanation: "ATP is the men's professional tour and WTA is the women's.",
    aliases: ["tour"],
  },
  {
    label: "Season",
    explanation: "A calendar year of matches.",
    aliases: ["season", "seasons"],
  },
  {
    label: "Return on investment (ROI)",
    explanation: "Profit divided by the total money staked. -5% means we lost 5 cents for every currency unit bet; anything above 0% means we made money.",
    aliases: ["ROI", "return on investment"],
    headers: ["ROI"],
  },
  {
    label: "Closing line value (CLV)",
    explanation: "How much better the odds we got were than the final odds just before the match. Final odds are the sharpest estimate of the truth, so consistently beating them suggests real skill even before profits show up.",
    aliases: ["CLV", "closing line value", "closing price", "closing prices"],
    headers: ["CLV"],
  },
  {
    label: "Confidence interval (95% CI)",
    explanation: "The range in which the true value very probably lies. If the range includes 0, we cannot rule out that the result is just luck.",
    aliases: ["95% CI", "confidence interval"],
    headers: ["ROI 95% CI", "CLV 95% CI", "CLV (95% CI)"],
  },
  {
    label: "Bootstrap",
    explanation: "A way to measure how much luck is involved: the same bets are re-sampled thousands of times in a computer, and the spread of the results gives the confidence interval.",
    aliases: ["bootstrap", "bootstrapping"],
  },
  {
    label: "Drawdown",
    explanation: "A fall from the highest point the money pot has reached. The maximum drawdown is the worst such fall and shows how painful the bad stretches were.",
    aliases: ["drawdown"],
  },
  {
    label: "Hit rate",
    explanation: "The share of bets that won.",
    aliases: ["hit rate"],
  },
  {
    label: "Brier score",
    explanation: "An accuracy score for win chances. 0 is perfect and 0.25 is no better than guessing 50/50; lower is better.",
    aliases: ["Brier score", "Brier"],
  },
  {
    label: "Log loss",
    explanation: "An accuracy score for win chances that punishes confident wrong guesses heavily. Lower is better.",
    aliases: ["log loss"],
  },
  {
    label: "θ (theta)",
    explanation: "The required gap: how much higher our own win chance must be than the bookmaker's before we bet. θ = 0.02 means 2 percentage points.",
    aliases: ["θ"],
    headers: ["θ"],
  },
  {
    label: "p-value",
    explanation: "How surprising the result would be if there were no real effect. A small p (below 0.05 by convention) means pure luck is an unlikely explanation.",
    aliases: ["p-value", "p-values"],
    headers: ["p"],
  },
  {
    label: "Bonferroni correction",
    explanation: "When many groups are tested, some will look special by luck alone. This correction makes the p-value stricter in proportion to the number of groups tested, so only strong results survive.",
    aliases: ["Bonferroni"],
    headers: ["p (Bonf.)", "p (Bonferroni)"],
  },
  {
    label: "In-sample / holdout",
    explanation: "In-sample seasons are the older ones we may study and tune on. The holdout seasons are kept unseen until the end, then looked at once, so the final test is honest.",
    aliases: ["in-sample", "out-of-sample", "holdout"],
  },
  {
    label: "Control (random bet)",
    explanation: "A coin-flip strategy that gets exactly the same bookmaker prices. Anything we claim as skill has to beat it, otherwise the result comes from the prices, not the idea.",
    aliases: ["control", "random_bet"],
    headers: ["Control CLV (random_bet)"],
  },
  {
    label: "Market-implied chance",
    explanation: "The win chance hidden in the bookmaker's odds, after taking out the bookmaker's built-in margin (no-vig). It is the market's best guess.",
    aliases: ["market-implied", "no-vig", "market price"],
    headers: ["Market-implied"],
  },
  {
    label: "Margin (overround / vig)",
    explanation: "The built-in profit of the bookmaker: odds are set so that the chances add up to more than 100%. It is why even coin-flip betting loses money in the long run.",
    aliases: ["overround", "margin", "vig"],
  },
  {
    label: "Elo rating",
    explanation: "A score for player strength that rises after wins and falls after losses, more so when the opponent was strong.",
    aliases: ["Elo"],
  },
  {
    label: "Fill book",
    explanation: "The bookmaker whose odds the simulated bets are placed at.",
    aliases: ["fill book", "fills"],
  },
  {
    label: "Favourite–longshot bias",
    explanation: "The observed tendency for bookmakers to charge more on unlikely winners than on likely ones, so long shots are worse value.",
    aliases: ["favourite–longshot bias", "favorite-longshot bias"],
  },
  {
    label: "Cohort",
    explanation: "A group of players or matches sharing one trait, such as a star sign.",
    aliases: ["cohort", "cohorts"],
  },
];

const escapeForRegex = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const aliasLookup = new Map<string, GlossaryEntry>(
  GLOSSARY.flatMap((entry) => entry.aliases.map((alias) => [alias.toLowerCase(), entry] as const)),
);

const headerLookup = new Map<string, GlossaryEntry>(
  GLOSSARY.flatMap((entry) => (entry.headers ?? []).map((header) => [header, entry] as const)),
);

const longestFirst = [...aliasLookup.keys()].sort((a, b) => b.length - a.length);
const TERM_PATTERN = new RegExp(
  `(?<![\\p{L}\\p{N}_])(?:${longestFirst.map(escapeForRegex).join("|")})(?![\\p{L}\\p{N}_])`,
  "giu",
);

export function lookupHeader(header: string): GlossaryEntry | undefined {
  return headerLookup.get(header);
}

export function findGlossaryTerms(text: string): GlossarySegment[] {
  const segments: GlossarySegment[] = [];
  const alreadyExplained = new Set<GlossaryEntry>();
  let cursor = 0;
  for (const match of text.matchAll(TERM_PATTERN)) {
    const entry = aliasLookup.get(match[0].toLowerCase());
    if (!entry || alreadyExplained.has(entry)) continue;
    alreadyExplained.add(entry);
    if (match.index > cursor) segments.push({ text: text.slice(cursor, match.index) });
    segments.push({ text: match[0], entry });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });
  return segments;
}

export function entryFor(alias: string): GlossaryEntry {
  const entry = aliasLookup.get(alias.toLowerCase());
  if (!entry) throw new Error(`no glossary entry for ${alias}`);
  return entry;
}
