# Build workflows and measured scope

The acceptance branch contains separate [real-source](../../../.github/workflows/project2-live.yml),
[Maps](../../../.github/workflows/project2-maps.yml), [development model](../../../.github/workflows/project2-model-smoke.yml),
[historical evaluation](../../../.github/workflows/project2-evaluate.yml) and
[frozen matrix](../../../.github/workflows/project2-agent-matrix.yml) workflows.
They run on Linux. A multi-OS portable-package matrix remains a plan; this branch
has no `project2.yml` workflow. Local Windows package checks do not certify
Linux/macOS installations or native ARM execution. Preserve skipped-test counts.

The workflows have explicit dispatch and scoped push triggers. The real-source
workflow also watches Project2 files, so even a documentation push can start it.
Documentation-only closure commits use `[skip ci]`; no successor or matrix rerun
is requested. A historical October11 push triggered [run38117973762](https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/38117973762),
which passed authored engine parity but failed to download a capture-checkpoint
artifact before source capture. Its [status and error](../examples/evidence/documentation-trigger-38117973762.json)
are retained; it was not retried and contains no new captured corpus or agent trial.
Ephemeral container shutdown is not proof of application cleanup or server recovery.

Version 9.5.5 was selected from the official
[Elastic Docker guide](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic),
checked on October 7, 2026 UTC. Subsequent real Linux executions qualified the
bounded Elasticsearch/Kibana combination on2,133,268 records, including three
rendered Maps cases; the actual agent study failed its quality gate. See the
[current measured acceptance](acceptance.md). This does not certify the separate
multi-OS package matrix above. The workflow uses GitHub's documented
[service-container lifecycle](https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers).
Container jobs require a Linux runner; running the regular package job alone
does not exercise Elasticsearch.

Artifact contents differ by workflow; inspect the specific run and its manifest
rather than assuming every artifact includes a wheelhouse or model. There is no
website deployment or qualified-release publication step. The
[distribution record](distribution.md) binds the verified Windows packages.
Backend, Maps and agent-quality gates remain separate.

Run the same Python commands locally from a checkout on capable user-controlled
hardware; GitHub Actions is optional and is not a runtime dependency. Full
offline infrastructure verification also requires pre-staged container images,
map/data/model assets, and an actual external-network-disabled experiment.
Before a later heavy job, inventory existing assets, reserve one host, budget
journals/scratch/archives and measure free RAM/disk. The [successor plan](agent-successor-plan.md)
is proposed only; it authorizes no launch, copy, cleanup or new acquisition.
