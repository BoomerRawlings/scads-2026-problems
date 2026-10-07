import { renderToString } from "react-dom/server";
import { expect, it } from "vitest";
import IntakeFlow, {
  GraphPlan,
  IntakeDiagram,
  ProfileSummary,
} from "./IntakeFlow";
import { initialStages } from "./intakeModel";
import type { IntakeProfile } from "./intakeTypes";

it("offers import and synthetic routes at first entry without starting a job", () => {
  const html = renderToString(
    <IntakeFlow workspace={null} onComplete={() => {}} />,
  );
  expect(html).toContain("Import a dataset");
  expect(html).toContain("View synthetic dataset");
  expect(html).toContain("10,000 people by default");
  expect(html).not.toContain("Continue existing workspace");
  expect(html).not.toContain("Build organization chart");
});

it("shows the workflow and planned size before generation can be requested", () => {
  const html = renderToString(
    <IntakeFlow
      workspace={null}
      initialMode="synthetic"
      onComplete={() => {}}
    />,
  );
  expect(html).toContain('aria-label="Dataset processing workflow"');
  expect(html).toContain("Planned individuals");
  expect(html).toContain("Measured after generation");
  expect(html).toContain('value="10000"');
  expect(html).toContain("Generate &amp; inspect");
  expect(html.match(/class="intake-stage queued/g)).toHaveLength(6);
  expect(html).not.toContain("Build organization chart");
});

it("shows source size before inspection and keeps unknown person count explicit", () => {
  const html = renderToString(
    <IntakeFlow workspace={null} initialMode="import" onComplete={() => {}} />,
  );
  expect(html).toContain("Source size");
  expect(html).toContain("Counted during inspection");
  expect(html).toContain("100 MB");
  expect(html).toContain(".tsv");
  expect(html).toContain(".mbx");
  expect(html).toContain('disabled="">');
});

it("labels playback separately from live work while preserving stage truth", () => {
  const stages = initialStages();
  stages[0].status = "complete";
  const html = renderToString(
    <IntakeDiagram
      stages={stages}
      selected="inspect"
      onSelect={() => {}}
      replay="inspect"
    />,
  );
  expect(html).toContain("Walkthrough replay");
  expect(html).toContain('aria-label="Step 1: Inspect source, Complete"');
  expect(html).toContain('aria-label="Step 4: Build the workspace, Up next"');
  expect(html).not.toContain("intake-spin");
});

it("source graph draws only edges whose endpoints are visible and labels its sample", () => {
  const html = renderToString(
    <GraphPlan
      plan={{
        nodes: [
          { id: "a", label: "A person", kind: "person" },
          { id: "b", label: "A unit", kind: "unit" },
        ],
        edges: [
          { source: "a", target: "b", relation: "member_of", origin: "model" },
          { source: "a", target: "missing", relation: "reports_to" },
        ],
        sampled: true,
        sample_nodes: 2,
        total_nodes: 10000,
        sample_edges: 2,
        total_source_relations: 12,
        note: "Supplied relationships only.",
      }}
    />,
  );
  expect(html).toContain(
    'aria-label="Source graph sample: 2 entities and 1 relationships"',
  );
  expect(html).toContain("Supplied relationships only.");
  expect(html).toContain("New reporting inferences are added later.");
  expect(html).toContain("member of");
  expect(html).toContain("Imported model proposal");
  expect(html).toContain('stroke-dasharray="5 4"');
});

it("reports distinct identities and absent fields without claiming verified authority", () => {
  const profile: IntakeProfile = {
    counts: {
      people: 10,
      entities: 12,
      units: 1,
      shared_mailboxes: 1,
      messages: 0,
      assertions: 3,
      evidence: 0,
      labels: 2,
      data_points: 15,
      communication_links: 0,
    },
    fields: [
      {
        id: "bodies",
        label: "Message bodies",
        present: 0,
        missing: 0,
        total: 0,
      },
    ],
    relations: [],
    quality: {
      read: 15,
      accepted: 15,
      duplicate: 0,
      quarantined: 0,
      unsupported: 0,
      issues: [],
      issue_count: 0,
    },
    notes: ["Missing information remains explicit."],
    timestamp_start: null,
    timestamp_end: null,
  };
  const html = renderToString(
    <ProfileSummary profile={profile} bytes={4096} />,
  );
  expect(html).toContain("Distinct person records");
  expect(html).toContain("4.0 KB");
  expect(html).toContain("isolated evaluation labels");
  expect(html).toContain('style="width:0%"');
  expect(html).not.toContain("NaN");
});
