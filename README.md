# Job Queue Microservices — Production-Ready Multi-Service Application

A broken four-service application taken to production: **16 bugs fixed,
containerized, orchestrated, wrapped in a six-gate CI/CD pipeline, and
deployed to AWS with health-verified rolling updates** — with every failure
along the way documented rather than hidden.

**Stack:** Node.js/Express (frontend) · Python/FastAPI (API) · Python worker ·
Redis 7 · Docker & Compose · GitHub Actions · Terraform · AWS (EC2, EIP, IAM,
SSM)

```
 Browser ──► Frontend (:3000) ──► API (:8000) ──► Redis ◄── Worker
                                         ▲    queue+status │
                                         └───── status ────┘
```

Jobs are processed asynchronously: the API returns a job id instantly, a
worker drains the Redis queue and marks completion, the browser polls status.
Full architecture: [docs/architecture.md](docs/architecture.md)

---

## Quick start (local)

Prerequisites: Docker with the Compose plugin, git.

```bash
git clone https://github.com/mosesekerin/job-queue-microservices.git
cd job-queue-microservices
cp .env.example .env          # then set a real REDIS_PASSWORD (openssl rand -hex 16)
docker compose up -d --build --wait
```

Verify the full journey of a job:

```bash
curl -X POST http://localhost:3000/submit          # → {"job_id": "..."}
curl http://localhost:3000/status/<JOB_ID>         # → "queued", then "completed" (~2s)
docker compose ps                                  # all four services (healthy)
```

Tear down: `docker compose down -v`

## Running the pipeline

Every push to `main` runs six chained gates — failure anywhere freezes
everything downstream:

**lint** (flake8 · eslint · hadolint) → **test** (pytest + fakeredis, coverage
artifact) → **build** (images tagged `<git-sha>` + `latest`, pushed to an
in-pipeline registry) → **security** (Trivy, fails on fixable CRITICALs) →
**integration** (full stack up on the runner, real job verified end-to-end) →
**deploy** (SSH rolling update; main-branch pushes only).

Deployment knows the server as exactly three repository secrets
(`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`) — the target is swappable
without touching the pipeline, which was verified in practice when the
instance was replaced.

## Documentation package

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Services, data flow, design decisions, failure-point analysis, known limitations |
| [FIXES.md](FIXES.md) | All 16 defects: location, root cause, fix, production impact |
| [docs/containerization.md](docs/containerization.md) | Dockerfile decisions: multi-stage vs single, non-root, healthchecks incl. the heartbeat pattern, build-time OS patching |
| [docs/orchestration-reliability.md](docs/orchestration-reliability.md) | Compose design, health-gated startup, resource limits, restart semantics, chaos drills |
| [docs/ci-pipeline.md](docs/ci-pipeline.md) | The six gates in detail + a taxonomy of every failure species encountered |
| [docs/deployment.md](docs/deployment.md) | Rolling-update mechanism, abort logic, deploy-phase debugging log |
| [docs/infrastructure-automation.md](docs/infrastructure-automation.md) | Terraform/IAM/SSM/user_data — "cattle, not pets" |
| [docs/engineering-journal.md](docs/engineering-journal.md) | The full chronological history: every error, pivot, and lesson |
| [docs/assets.md](docs/assets.md) | Diagrams and recommended screenshots |
| [.env.example](.env.example) | Required environment variables with placeholders |

Milestone documents from the working history (tagged in git):
MILESTONE-01 (containerization, `v0.2.0-containerized`) · MILESTONE-02
(orchestration & reliability, `v0.3.0-orchestrated`) · MILESTONE-03
(CI pipeline, `v0.4.0-ci`).

## Engineering highlights

- **A race condition fixed by reordering two lines** — and the same principle
  ("make things visible only when fully ready") later reused as the design of
  health-gated startup and the rolling deploy.
- **A portless worker's pulse taken via a heartbeat file** — liveness for a
  process nothing ever connects to.
- **A production-only crash found and fixed after deployment** (Redis
  TimeoutError escaping a too-narrow except) — absorbed by the restart policy
  until the root cause shipped through the pipeline: defense in depth observed
  live.
- **The security gate tuned against reality:** fail on fixable CRITICALs,
  report unfixable ones — after both cases actually occurred.
- **Every gate was seen to fail at least once.** The red runs are documented;
  they are the evidence the gates work.

## Security posture

Non-root containers · slim, build-time-patched bases · Redis password-enforced
and never exposed externally · no secrets in code, images, or Terraform state
(SSM Parameter Store + IAM instance role) · dedicated single-purpose deploy
key · pinned dependencies and lockfile · `.env` git-ignored with a committed
`.env.example`.

**Documented trade-offs:** SSH open to 0.0.0.0/0 with key-only auth (GitHub
runners have unpredictable IPs); frontend swap has a ~1–2s blip (host port
binding); a SIGKILLed worker loses its in-flight job (pop-before-process).
Each has a named upgrade path below.

## Planned Future Work (discussed, not completed)

- **Sabotage drill:** deliberately break `/health`, push, and observe the
  rolling deploy abort while the live site keeps serving the old version.
- **v1.0.0 release tag** upon completion of the final phase.
- **Infrastructure automation acceptance test:** terraform apply replacing the
  instance, then a job completing via curl on a machine no human has SSH'd
  into (implementation written; final apply/verification pending — see
  docs/infrastructure-automation.md).
- **Build-once, deploy-the-same-artifact:** push CI-built, Trivy-scanned,
  SHA-tagged images to a real registry (ECR/GHCR); the server pulls instead of
  rebuilding — closing the gap where production rebuilds a sibling of the
  scanned image.
- **Reverse proxy in front of the frontend** for true zero-downtime swaps.
- **Ack-after-processing queue semantics** so a SIGKILLed worker cannot lose
  an in-flight job.
- Smaller items: distroless base evaluation; scheduled image rebuilds (images
  rot); flake8 config in `setup.cfg`; restricting SSH/monitoring CIDRs;
  re-running SSL issuance after instance replacement; slim user_data that
  fetches a versioned bootstrap script.

---

*This repository's documentation is a factual reconstruction of the project's
engineering history, including failures and corrected mistakes. See
[docs/engineering-journal.md](docs/engineering-journal.md) for the
chronological account.*
