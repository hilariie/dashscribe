import type { AdviceClass } from "../types";

// Source-of-truth for urgency-related lexicons. Keep additions here so the
// classifier and the keyword check stay in sync. Word matches are
// case-insensitive and operate on tokenised lowercase substrings.
export const URGENCY = {
  // Verbs that follow "Advice:". Order matters: longer/more-specific phrases
  // first so "prepare to stop" is matched as cautious before "stop" classifies
  // it as urgent.
  cautiousVerbs: ["slow down", "prepare to stop", "watch", "ease"],
  urgentVerbs: ["brake", "stop", "swerve", "evade", "emergency"],
  calmVerbs: ["maintain", "hold", "continue"],
  // Observation-side keywords that escalate even if the Advice clause did not.
  observationKeywords: [
    "collision",
    "crash",
    "impact",
    "debris",
    "closing in",
    "imminent",
    "swerve",
  ],
} as const;

const CLASS_RANK: Record<AdviceClass, number> = {
  calm: 0,
  cautious: 1,
  urgent: 2,
};

// Split on the literal "Advice:" — the locked prompt format guarantees this
// shape. Returns { observation, advice } with both lowercase-trimmed.
export function splitObservationAdvice(text: string): {
  observation: string;
  advice: string;
} {
  const idx = text.toLowerCase().indexOf("advice:");
  if (idx === -1) {
    return { observation: text.toLowerCase().trim(), advice: "" };
  }
  return {
    observation: text.slice(0, idx).toLowerCase().trim(),
    advice: text
      .slice(idx + "advice:".length)
      .toLowerCase()
      .trim(),
  };
}

export function classifyAdvice(text: string): AdviceClass {
  const { advice } = splitObservationAdvice(text);
  if (advice === "") return "calm";
  // Cautious phrases checked first so "prepare to stop" doesn't get misclassified
  // as urgent on the bare "stop" match.
  for (const phrase of URGENCY.cautiousVerbs) {
    if (advice.includes(phrase)) return "cautious";
  }
  for (const phrase of URGENCY.urgentVerbs) {
    if (advice.includes(phrase)) return "urgent";
  }
  for (const phrase of URGENCY.calmVerbs) {
    if (advice.includes(phrase)) return "calm";
  }
  return "calm";
}

export function containsUrgencyKeyword(text: string): boolean {
  const lower = text.toLowerCase();
  return URGENCY.observationKeywords.some((kw) => lower.includes(kw));
}

export function escalates(prev: AdviceClass, next: AdviceClass): boolean {
  return CLASS_RANK[next] > CLASS_RANK[prev];
}
