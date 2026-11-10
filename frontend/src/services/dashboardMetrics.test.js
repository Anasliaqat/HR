import { describe, expect, it } from "vitest";
import { getApplicationTrend } from "./dashboardMetrics";

describe("getApplicationTrend", () => {
  it("counts real applications for the last seven local calendar days", () => {
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const outsideRange = new Date(today);
    outsideRange.setDate(outsideRange.getDate() - 7);

    const trend = getApplicationTrend([
      { applied_at: today.toISOString() },
      { applied_at: today.toISOString() },
      { applied_at: yesterday.toISOString() },
      { applied_at: outsideRange.toISOString() },
      { applied_at: "not-a-date" },
    ]);

    expect(trend).toHaveLength(7);
    expect(trend.at(-1).count).toBe(2);
    expect(trend.at(-2).count).toBe(1);
    expect(trend.reduce((total, day) => total + day.count, 0)).toBe(3);
  });
});
