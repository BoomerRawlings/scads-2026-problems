import { describe, expect, it } from "vitest";
import {
  directoryRecovery,
  distinctSnapshotPair,
  reviewEntry,
} from "./explorerGuidance";
import type { Assertion } from "./types";

const assertion = (
  id: string,
  reporting_type = "primary",
  review_status = "unreviewed",
) => ({ id, reporting_type, review_status }) as Assertion;

describe("empty directory recovery", () => {
  it("offers a useful review starting point instead of implying missing people", () => {
    const recovery = directoryRecovery("", "reviewed", 0);
    expect(recovery.title).toBe("No reviewed relationships yet");
    expect(recovery.action).toBe("clear_filters");
  });
  it("clears restrictive search/filter before proposing another import", () => {
    expect(directoryRecovery("Nobody", "all", 0).action).toBe("clear_filters");
    expect(directoryRecovery("", "unresolved", 80).action).toBe(
      "clear_filters",
    );
  });
  it("recovers an empty page without replacing a dataset", () => {
    expect(directoryRecovery("", "all", 80).action).toBe("first_page");
    expect(directoryRecovery("", "all", 0).action).toBe("import");
  });
});

describe("review entry", () => {
  it("opens manager assignment when no proposal can be reviewed", () => {
    expect(reviewEntry([])).toEqual({ action: "replace", assertionId: "" });
    expect(reviewEntry([assertion("matrix", "matrix")], "matrix").action).toBe(
      "replace",
    );
  });
  it("uses a primary proposal when a read-only matrix relationship is selected", () => {
    expect(
      reviewEntry([assertion("m", "matrix"), assertion("p")], "m"),
    ).toEqual({ action: "accept", assertionId: "p" });
  });
  it("keeps a chosen alternative and avoids accepting an already accepted relation again", () => {
    expect(reviewEntry([assertion("a"), assertion("b")], "b").assertionId).toBe(
      "b",
    );
    expect(
      reviewEntry([assertion("a", "primary", "accepted")], "a").action,
    ).toBe("replace");
  });
});

describe("comparison recovery", () => {
  it("requires two distinct snapshots", () => {
    expect(distinctSnapshotPair([])).toBeNull();
    expect(distinctSnapshotPair(["a", "a"])).toBeNull();
  });
  it("compares the oldest other snapshot against the latest active one", () => {
    expect(distinctSnapshotPair(["new", "mid", "old"], "new")).toEqual({
      before: "old",
      after: "new",
    });
    expect(distinctSnapshotPair(["new", "old"], "missing")).toEqual({
      before: "old",
      after: "new",
    });
    expect(distinctSnapshotPair(["new", "old"], "old")).toEqual({
      before: "new",
      after: "old",
    });
  });
});
