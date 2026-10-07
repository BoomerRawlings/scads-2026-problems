import type { Assertion } from "./types";

export function directoryRecovery(
  search: string,
  status: string,
  offset: number,
) {
  if (search.trim() || status !== "all")
    return {
      title:
        status === "reviewed" && !search.trim()
          ? "No reviewed relationships yet"
          : "No people match these filters",
      description:
        status === "reviewed" && !search.trim()
          ? "Choose a person and inspect their evidence before recording a review."
          : "Clear the search and relationship filter to return to everyone.",
      action: "clear_filters" as const,
      label: "Show everyone",
    };
  if (offset > 0)
    return {
      title: "No people on this page",
      description: "The dataset may have changed. Return to the first page.",
      action: "first_page" as const,
      label: "Return to first page",
    };
  return {
    title: "This dataset has no people",
    description:
      "Import a roster or communications with identifiable senders and recipients.",
    action: "import" as const,
    label: "Import a dataset",
  };
}

// Opening review must always lead to a usable form, including unresolved people.
// This selects a form only; the analyst must still provide a reason and save.
export function reviewEntry(assertions: Assertion[], activeId?: string) {
  const active = assertions.find((item) => item.id === activeId);
  const candidate =
    active?.reporting_type !== "matrix" && active
      ? active
      : assertions.find((item) => item.reporting_type !== "matrix");
  return {
    action:
      candidate && candidate.review_status !== "accepted"
        ? "accept"
        : "replace",
    assertionId: candidate?.id || "",
  };
}

export function distinctSnapshotPair(
  ids: string[],
  preferredAfter?: string | null,
) {
  const unique = [...new Set(ids)];
  if (unique.length < 2) return null;
  const after =
    preferredAfter && unique.includes(preferredAfter)
      ? preferredAfter
      : unique[0];
  return { before: [...unique].reverse().find((id) => id !== after)!, after };
}
