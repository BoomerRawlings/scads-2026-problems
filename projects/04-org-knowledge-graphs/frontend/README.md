# Organization Atlas frontend

Local React / TypeScript analyst workspace. All organization data comes from the same-origin `/api`; no mock records or external network resources are used.

```powershell
npm ci
npm run build
npm test
```

The FastAPI service serves `dist/`. For development, start that service at `127.0.0.1:8764`, then `npm run dev`. Vite proxies API requests while preserving the original host for same-origin write validation. Node 22.12+ or 24+ is recommended by the pinned build tools.

The SVG renderer uses deterministic hierarchy layout over a bounded API response (30, 80, or 200 nodes). The directory, table, and focus navigation cover larger corpora without sending the complete organization to the renderer. The initial viewport preserves readable card size; independent trees are packed into shelves. Graph controls provide pan, zoom, full-scene fit, focus, and keyboard node selection. Four layout tests check reporting depth, sibling separation, unresolved/cyclic payload handling, determinism, and compact forest packing.

Main workflows: import or explicitly load the fictional corpus; infer; search/filter/page; inspect relationship alternatives and cited evidence; accept/reject/replace/undo with a reason; inspect formal units and inferred groups; compare snapshots; export canonical JSON, lossy CSV, or an analyst report. Historical snapshots are read-only. Raw scores are never presented as probabilities.

Icons are imported individually. Production source maps and whole-program tree-shaking are disabled to avoid excessive bundler work on the analytical JSX; esbuild still minifies the small, explicitly imported module set.
