import { renderToString } from "react-dom/server";
import { expect, it } from "vitest";
import SemanticChart from "./SemanticChart";

it("renders the first loading frame with navigation before chart data exists", () => {
  const html = renderToString(
    <SemanticChart
      snapshot="snapshot-test"
      version={7}
      limit={30}
      selected={null}
      focus={null}
      onSelect={() => {}}
      onFocus={() => {}}
    />,
  );
  expect(html).toContain("Organization");
  expect(html).toContain('aria-label="Zoom in"');
  expect(html).toContain('aria-label="Zoom out"');
  expect(html).toContain("Loading this level");
  expect(html).toContain("Communication groups");
  expect(html).toContain('<option value="zoom" selected="">Zoom</option>');
});
