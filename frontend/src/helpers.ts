import type { Status } from "./types";

export const STATUSES: Status[] = ["Wishlist", "Applied", "Interviewing", "Archived"];

export const initials = (company: string) =>
  company.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();

export function formatPostedDate(postedAt: string | null) {
  return postedAt
    ? new Date(`${postedAt}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    : "Unknown";
}
