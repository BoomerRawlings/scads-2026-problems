# Portable build and live parity jobs

The repository's [Project 2 workflow](../../../.github/workflows/project2.yml)
defines Python 3.12 checks on Windows, Linux and macOS, plus Python 3.13 on Linux.
Each job runs the full tests and builds both a core wheel and a bundle containing
the optional MCP and geometry dependencies. Each bundle gets a fresh offline
installation smoke outside the source checkout. Native dependency wheels belong
to that job's Python, OS and CPU architecture; use its release manifest when
choosing a target machine.

The workflow is configured, **not executed or certified from this development
session**. Local Windows evidence does not establish Linux/macOS support. The
test report must retain skipped tests, including optional features or platform
privileges, rather than presenting every collected test as passed.

Push and pull-request triggers are limited to Project 2 paths. Manual dispatch
also exposes `run_elasticsearch`, disabled by default. Enabling it starts a fresh
loopback-only Elasticsearch 9.5.5 container on the Linux runner and executes the
[live parity runner](live-parity.md). It uses synthetic fixture records only,
creates its own dedicated index and requests ownership-checked cleanup. The
container is ephemeral; its disappearance is not evidence of application cleanup.

Version 9.5.5 is a candidate selected from the official
[Elastic Docker guide](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic),
checked on October 7, 2026 UTC. It becomes a verified project combination only
after successful real execution. The workflow uses GitHub's documented
[service-container lifecycle](https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers).
Container jobs require a Linux runner; running the regular package job alone
does not exercise Elasticsearch.

Artifacts contain the wheelhouse, checksum/verification manifests, and live
parity evidence when that job runs. There is no publication or deployment step,
and workflow permissions are read-only. Kibana rendering, official NTA data,
real NYC capture, million-record scale and agent quality remain separate gates.

Run the same Python commands locally from a checkout on capable user-controlled
hardware; GitHub Actions is optional and is not a runtime dependency. Full
offline infrastructure verification also requires pre-staged container images,
map/data/model assets, and an actual external-network-disabled experiment.
