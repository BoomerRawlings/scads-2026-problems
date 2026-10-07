import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ChartTooltip, {
  edgeTooltip,
  nodeTooltip,
  tooltipPosition,
} from "./ChartTooltip";
import type { TooltipNode } from "./ChartTooltip";

const person: TooltipNode = {
  name: "Ada Stone",
  kind: "person",
  person_count: 1,
  role: "Research lead",
  status: "unresolved",
  children_count: 0,
  expandable: true,
};

describe("chart hover information", () => {
  it("shows a position and zero reports without inventing an unknown manager", () => {
    const content = nodeTooltip(person);
    expect(content.subtitle).toBe("Research lead");
    expect(content.rows).toContainEqual({
      label: "Direct reports",
      value: "0",
    });
    expect(content.rows.some((row) => row.label === "Reports to")).toBe(false);
    expect(content.rows).toContainEqual({
      label: "Status",
      value: "Unresolved",
    });
  });

  it("includes a known manager and optional email", () => {
    const content = nodeTooltip(
      { ...person, manager_name: "Prior name", email: "ada@example.test" },
      "Rowan Hale",
    );
    expect(content.rows).toContainEqual({
      label: "Reports to",
      value: "Rowan Hale",
    });
    expect(content.rows).toContainEqual({
      label: "Email",
      value: "ada@example.test",
    });
  });

  it("distinguishes inferred communication groups from formal authority", () => {
    const content = nodeTooltip({
      ...person,
      kind: "group",
      person_count: 1024,
      unresolved_count: 0,
    });
    expect(content.notice).toContain("not a verified formal reporting unit");
    expect(content.notice).toContain("memberships can overlap");
    expect(content.rows).toContainEqual({
      label: "Reporting unresolved",
      value: "0",
    });
  });

  it("identifies reporting branches as presentation groups", () => {
    expect(nodeTooltip({ ...person, kind: "team" }).notice).toContain(
      "presentation group",
    );
    expect(nodeTooltip({ ...person, kind: "team" }).notice).toContain(
      "not an additional formal department",
    );
  });

  it("keeps manager direction correct and never formats raw scores as probability", () => {
    const content = edgeTooltip(
      {
        id: "a",
        source: "manager",
        target: "report",
        origin: "model",
        review_status: "accepted",
        raw_score: 0.82,
        calibration_status: "uncalibrated",
      },
      "Rowan Hale",
      "Ada Stone",
    );
    expect(content.title).toBe("Ada Stone");
    expect(content.rows).toContainEqual({
      label: "Reports to",
      value: "Rowan Hale",
    });
    expect(content.rows).toContainEqual({
      label: "Raw model score",
      value: "0.820 · not a probability",
    });
    expect(content.rows).toContainEqual({ label: "Review", value: "Accepted" });
    expect(content.notice).toContain("not a calibrated probability");
  });

  it("does not invent a score for a source connection", () => {
    const content = edgeTooltip(
      {
        id: "a",
        source: "manager",
        target: "report",
        origin: "source",
        review_status: "unreviewed",
        raw_score: null,
        calibration_status: "not_applicable",
      },
      "Rowan Hale",
      "Ada Stone",
    );
    expect(content.rows.some((row) => row.label === "Raw model score")).toBe(
      false,
    );
    expect(content.notice).toBeUndefined();
  });

  it("provides an accessible noninteractive tooltip only while open", () => {
    const props = {
      anchor: { x: 100, y: 80 },
      bounds: { width: 600, height: 500 },
      id: "test-hover",
    };
    expect(renderToString(<ChartTooltip {...props} content={null} />)).toBe("");
    const html = renderToString(
      <ChartTooltip {...props} content={nodeTooltip(person)} />,
    );
    expect(html).toContain('role="tooltip"');
    expect(html).toContain('id="test-hover"');
    expect(html).toContain("Research lead");
    expect(html).not.toContain("<button");
  });
});

describe("chart tooltip placement", () => {
  it("appears beside the pointer when there is room", () => {
    expect(
      tooltipPosition(
        { x: 30, y: 40 },
        { width: 800, height: 600 },
        { width: 290, height: 230 },
      ),
    ).toMatchObject({ left: 46, top: 58, width: 290 });
  });

  it("flips left and above at the bottom right", () => {
    const point = tooltipPosition(
      { x: 790, y: 590 },
      { width: 800, height: 600 },
      { width: 290, height: 230 },
    );
    expect(point.left).toBe(484);
    expect(point.top).toBe(342);
  });

  it("constrains a large tooltip to a narrow chart", () => {
    const point = tooltipPosition(
      { x: 180, y: 150 },
      { width: 200, height: 180 },
      { width: 290, height: 400 },
    );
    expect(point).toEqual({ left: 8, top: 8, width: 184, maxHeight: 164 });
  });
});
