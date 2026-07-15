# Deployment

## Design question that produced the mechanism

A naive deploy (stop old → start new) inflicts an outage window on every user
who clicks during the gap — and if the new container is broken, the working
thing was destroyed before its replacement was proven. The careful order is
the Stage 2 race-condition principle at deployment scale: **make things
visible only when fully ready.**

## The rolling update (deploy.sh)

For each stateless service (api, worker):

1. **START** the new container **alongside** the old
   (`docker compose up -d --no-deps --no-recreate --scale svc=2`) — the old
   never stops serving. Two workers briefly draining one queue is the scaling
   model working as designed.
2. **WAIT** for the newcomer to prove itself: poll
   `docker inspect -f '{{.State.Health.Status}}'` with a hard **60-second
   deadline** — the Stage 3 healthchecks are the judge.
3. **ABORT** if never healthy: remove the new container and `exit 1` (fails
   the pipeline loudly). The old container never noticed anything; users never
   saw a broken second.
4. **CUTOVER** if healthy: stop and remove the old container peacefully.

**Frontend exception (documented limitation):** it binds a host port, and two
containers cannot share one door. The new image is proven with a **canary**
(temporary container on the network, no port); only after it turns healthy is
the real frontend fast-recreated (~1–2s blip). True zero-downtime requires a
reverse proxy in front — named as the upgrade path, not hidden.

## The pipeline's deploy job

- Gated: `needs: integration` + `if: push to main` — nothing reaches the
  server unproven; PRs run checks but never deploy.
- Target-agnostic by construction: the job knows the server as **three
  repository secrets only** (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`)
  and does `ssh ... "cd <app dir> && git pull && ./deploy.sh"`. Swapping the
  target machine changes three secret values and nothing else — verified when
  the instance was later replaced (Elastic IP kept even the host value stable).
- Dedicated deploy keypair (never a personal key): one purpose, one
  credential, independently revocable.

## Production debugging log (deploy phase)

- **Secret evaluated to null:** debug logs showed `DEPLOY_SSH_KEY => null`
  while the others showed `***`. Forensic rule learned: `***` = present but
  masked; null/empty = absent. The null cascaded into an empty key file,
  `error in libcrypto`, `Permission denied (publickey)`.
- **"REMOTE HOST IDENTIFICATION HAS CHANGED":** the instance had been
  replaced — new host keys, same IP. Everything hand-configured on the old
  instance was gone; this pain is the direct motivation for the
  infrastructure automation phase.
- **Server-side session:** three self-diagnosed faults in one sitting —
  compose v1 vs v2 (`unknown shorthand flag: -d`), wrong working directory
  (`no configuration file provided`), and the predicted Grafana port collision
  (`failed to bind 0.0.0.0:3000`) traced to a misplaced `.env` one directory
  above where compose reads it.
- **Path bug caught in review:** the pipeline's `cd` target didn't match the
  actual nested clone path on the server; corrected before it could fail.
- **First automated deployment succeeded** and shipped a real fix
  (FIXES.md #16) via rolling update onto the live server.

## Verified end state

Full chain green: push → lint → test → build → security → integration →
SSH deploy → rolling update → live curl returns a job that completes.
