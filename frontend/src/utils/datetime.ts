export function formatZonedDateTime(
  utcIso: string,
  timezone: string,
): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
    hour12: true,
  }).format(new Date(utcIso));
}

export function formatUtcDateTime(utcIso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    dateStyle: "medium",
    timeStyle: "short",
    hour12: false,
  }).format(new Date(utcIso));
}

export function formPartsFromLocalIso(localIso: string): {
  date: string;
  time: string;
} {
  const [date = "", timeWithOffset = ""] = localIso.split("T");
  return { date, time: timeWithOffset.slice(0, 5) };
}

export function joinLocalDateTime(date: string, time: string): string {
  return date && time ? `${date}T${time}` : "";
}

export function previewLocalDateTime(date: string, time: string): string {
  if (!date || !time) {
    return "Choose a future date and time";
  }
  return `${date} at ${time}`;
}
