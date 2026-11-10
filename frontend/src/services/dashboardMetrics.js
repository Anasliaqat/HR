export function getApplicationTrend(applications) {
  const today = new Date();
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today);
    date.setHours(0, 0, 0, 0);
    date.setDate(today.getDate() - (6 - index));
    return {
      date,
      label: date.toLocaleDateString(undefined, { weekday: "short" }),
    };
  });
  const countsByDate = new Map(
    days.map(({ date }) => [date.toLocaleDateString(), 0]),
  );
  for (const application of applications) {
    const appliedAt = new Date(application.applied_at);
    if (Number.isNaN(appliedAt.getTime())) continue;
    const key = new Date(
      appliedAt.getFullYear(),
      appliedAt.getMonth(),
      appliedAt.getDate(),
    ).toLocaleDateString();
    if (countsByDate.has(key)) {
      countsByDate.set(key, countsByDate.get(key) + 1);
    }
  }
  return days.map(({ date, label }) => ({
    label,
    count: countsByDate.get(date.toLocaleDateString()) ?? 0,
  }));
}
