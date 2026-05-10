import { describe, expect, it } from "vitest";
import {
  classifyAdvice,
  containsUrgencyKeyword,
  escalates,
  splitObservationAdvice,
} from "./urgency";

describe("splitObservationAdvice", () => {
  it("splits on 'Advice:' literal", () => {
    expect(
      splitObservationAdvice("Lead car braking. Advice: brake now."),
    ).toEqual({ observation: "lead car braking.", advice: "brake now." });
  });

  it("returns observation only when no Advice clause", () => {
    expect(splitObservationAdvice("clear road, nothing to do")).toEqual({
      observation: "clear road, nothing to do",
      advice: "",
    });
  });

  it("is case-insensitive on the marker", () => {
    expect(
      splitObservationAdvice("X. ADVICE: hold lane.").advice,
    ).toBe("hold lane.");
  });
});

describe("classifyAdvice", () => {
  it("classifies maintain/hold/continue as calm", () => {
    expect(classifyAdvice("Foo. Advice: maintain speed.")).toBe("calm");
    expect(classifyAdvice("Foo. Advice: hold lane.")).toBe("calm");
    expect(classifyAdvice("Foo. Advice: continue.")).toBe("calm");
  });

  it("classifies brake/swerve/stop as urgent", () => {
    expect(classifyAdvice("Foo. Advice: brake now.")).toBe("urgent");
    expect(classifyAdvice("Foo. Advice: brake hard.")).toBe("urgent");
    expect(classifyAdvice("Foo. Advice: swerve right.")).toBe("urgent");
    expect(classifyAdvice("Foo. Advice: emergency stop.")).toBe("urgent");
  });

  it("classifies slow down / prepare to stop as cautious (not urgent)", () => {
    // The 'stop' substring would match urgent if order were wrong; this guards
    // the lookup-order invariant in classifyAdvice.
    expect(classifyAdvice("Foo. Advice: prepare to stop.")).toBe("cautious");
    expect(classifyAdvice("Foo. Advice: slow down.")).toBe("cautious");
  });

  it("tolerates whitespace and case in input", () => {
    expect(classifyAdvice("  FOO.   ADVICE:    BRAKE NOW.   ")).toBe("urgent");
  });

  it("returns calm when there is no Advice clause (graceful default)", () => {
    expect(classifyAdvice("just a fragment, no advice")).toBe("calm");
  });
});

describe("containsUrgencyKeyword", () => {
  it("detects collision", () => {
    expect(containsUrgencyKeyword("Collision imminent ahead.")).toBe(true);
  });
  it("detects 'closing in' multi-word phrase", () => {
    expect(containsUrgencyKeyword("Vehicle closing in fast.")).toBe(true);
  });
  it("returns false on calm observations", () => {
    expect(containsUrgencyKeyword("Empty highway, clear conditions.")).toBe(
      false,
    );
  });
  it("is case-insensitive", () => {
    expect(containsUrgencyKeyword("CRASH ahead!")).toBe(true);
  });
});

describe("escalates", () => {
  it("calm -> urgent escalates", () => {
    expect(escalates("calm", "urgent")).toBe(true);
  });
  it("calm -> cautious escalates", () => {
    expect(escalates("calm", "cautious")).toBe(true);
  });
  it("cautious -> urgent escalates", () => {
    expect(escalates("cautious", "urgent")).toBe(true);
  });
  it("urgent -> urgent does not escalate (no chained preempts)", () => {
    expect(escalates("urgent", "urgent")).toBe(false);
  });
  it("urgent -> calm does not escalate (don't preempt downwards)", () => {
    expect(escalates("urgent", "calm")).toBe(false);
  });
  it("calm -> calm does not escalate", () => {
    expect(escalates("calm", "calm")).toBe(false);
  });
});
