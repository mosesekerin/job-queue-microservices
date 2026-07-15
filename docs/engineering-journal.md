# Engineering Journal — the full history, chronologically

A factual record of how this project actually went: decisions, wrong turns,
failures, and what each one taught. Nothing here is reconstructed from
imagination; every entry traces to a terminal session or pipeline run.

## Phase 0 — Sequencing decision
Opening question: "shouldn't we provision infrastructure first?" Decision: no —
the app defines infrastructure requirements, not the other way around; stages
1–6 are infrastructure-agnostic; provision a minimum viable target at deploy
time; write the deploy stage target-agnostic (SSH + variables) so swapping the
box later changes nothing. Every part of that plan was later exercised,
including the box swap.

## Phase 1–2 — Understanding and fixing (15 issues → FIXES.md)
Highlights: the queue/status race condition reasoned out from first principles
(and the lesson that a sleep is never a safety mechanism); silent failures
replaced with retry loops, honest status codes, and operator logs; the
committed secret removed and the .gitignore discipline installed; dependency
pinning done from reality (`pip freeze`, committed lockfile) after discovering
the caret range `^4.18.2` had silently resolved to 4.22.2.

## Local baseline
The whole system run bare on the host before containerizing — if it works
locally and breaks in Docker, the fault is the Docker layer. Errors met:
`tls: bad record MAC` (transient download corruption — retry, not
soul-searching) and `externally-managed-environment` (modern Ubuntu protecting
its system Python → per-project venvs; the offered `--break-system-packages`
shortcut declined on principle).

## Phase 3 — Containerization
Predicted, then observed: with no env vars, every service hunted Redis at
localhost — inside a container, localhost is the container itself. The broken
system failed *loudly and honestly* (worker retrying every 3s with the exact
error; frontend returning `{"error":"api unavailable"}`) — the Phase 2 fixes
proving themselves during a failure. Fix: shared network + name-based
discovery. Both healthcheck failures (API /health 404: endpoint not actually
added; worker unhealthy: heartbeat lines missing) fixed via the core cycle
edit → rebuild → replace. A misread error ("No such container: redis" — which
belonged to the cleanup command, not the run) taught: match each error to the
command that produced it. Milestone tag: v0.2.0-containerized.

## Phase 4–5 — Orchestration and chaos drills
Compose replaced hand-typed commands; startup order predicted from the
dependency tree and confirmed against the `--wait` timestamps; Redis auth
verified both ways. Drills: dependency outage (graceful degradation observed;
liveness-vs-readiness understood), SIGKILL crash (exit 137 literacy;
stop/kill/rm ladder), and the restart-policy episode in which the mentor's
model was wrong and the terminal proved it — `docker kill` counts as operator
intent; only deaths Docker didn't cause trigger `unless-stopped`. Honest crash
simulation via host-side `kill -9` verified resurrection. Milestone tag:
v0.3.0-orchestrated.

## Phase 6 — The six-gate pipeline
Built gate by gate, with a prediction committed before every run. Failures, in
order: flake8 style findings (first run; formatters adopted); a local flake8
avalanche from linting .venv (exclude what git excludes); the 28-minute pytest
hang (import runs the file; `__main__` guard); coverage dropping 84%→55% as
the measurement became truthful; a nonexistent Trivy action version
(pipeline-definition failure — verify versions against reality); unfixable
perl CRITICALs (policy tuned: ignore-unfixed); fixable gnutls CRITICALs
(legitimate catch → build-time apt upgrade everywhere); lint catching the lost
heartbeat (F401 as smoke from a real fire). Integration passed first try, as
predicted from the architecture. Milestone tag: v0.4.0-ci.

## Phase 7 — Deployment
The rolling-update order derived by the engineer from the race-condition
principle before any script was shown: start new beside old → wait healthy
(60s) → cut over, else kill the newcomer while the old keeps serving. Deploy
job written against three secrets only. Incidents: `DEPLOY_SSH_KEY => null`
(***-vs-null forensics); the host-key-changed warning revealing the instance
had been silently replaced (and everything hand-configured with it); a
self-diagnosed server session (compose v1 vs v2, wrong directory, the
predicted Grafana 3000 collision traced to a misplaced .env); a pipeline path
bug caught in review. First automated deployment succeeded — and shipped fix
#16, a production-only crash (TimeoutError escaping a too-narrow except)
that the restart policy had been absorbing. Defense in depth, live.

## Phase 8 — Infrastructure automation (in progress at time of writing)
Every manual server step moved to Terraform: IAM role + SSM for secrets,
user_data Section 13 for bootstrap, deploy key as a piped variable, UFW and
compose-v2 fixed at the source. Incident: the 16KB user_data limit (base64
inflation) → `base64gzip`. Acceptance test defined: a job completing on a
replaced instance no human has touched.

## Recurring principles (the ones that appeared in 3+ costumes)
- Make things visible only when fully ready (race fix → health-gated startup →
  rolling deploys).
- Never proceed on unproven ground (service_healthy → needs: → deploy gating).
- Reproducibility (pins, lockfiles, frozen images, hermetic tests, cattle).
- Config outside code; secrets outside config.
- Loud failure beats silent failure; logs for humans, exit codes for machines.
- Timing numbers are local measurements, not laws.
- Predict before you run; when reality contradicts the model, fix the model —
  even when the model came from the mentor.
