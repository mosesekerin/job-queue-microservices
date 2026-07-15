# Infrastructure Automation (final phase)

## Motivation — "cattle, not pets"

The EC2 host was prepared by hand (Docker install, usermod, clone, .env,
authorized_keys). When the instance was silently replaced, all of it
evaporated — hand-typed setup dies with the instance; automated setup is
resurrected with it. This phase moves every manual step into the
infrastructure repository (hng-infrastructure), keeping the two-pipeline
separation by lifecycle: the infra pipeline produces a running box; the app
pipeline deploys onto whatever box its three secrets point at.

## Components

1. **Secret channel — AWS SSM Parameter Store.** The Redis password is created
   once, manually, outside Terraform
   (`aws ssm put-parameter --name /microapp/prod/redis_password --type SecureString ...`)
   because anything Terraform creates lands in its state file in plaintext.
   Terraform manages the *permission to read*; the value enters through a side
   door. The path `/microapp/<env>/...` is a project-invented naming contract
   that three places must agree on letter-for-letter: the put-parameter
   command, the IAM policy resource ARN, and the boot-script fetch.
2. **Instance identity — IAM role + instance profile** (new
   `modules/compute/iam.tf`): the machine may `ssm:GetParameter` under
   `/microapp/prod/*` and nothing else. No credential exists anywhere; AWS
   recognizes the machine itself. Least privilege, one action, one path.
3. **user_data Section 13 — app bootstrap on first boot:** authorize the CI/CD
   deploy public key in `authorized_keys`; `git clone URL PATH` to the exact
   directory the pipeline expects (the two-argument clone form avoids the
   nested-folder trap of bare clone); fetch the password from SSM via the
   instance role and write a root-only `.env` (with `FRONTEND_PORT=3001`);
   chown to ubuntu so the pipeline's `git pull` works; first
   `docker compose up -d --build` creates the world the deploy script later
   evolves. Also fixed at the source: install `docker-compose-v2` (the old
   script installed legacy v1 — the reason `docker compose` was missing during
   manual setup) and `ufw allow 3001` (the app had worked *despite* UFW only
   because Docker's published ports bypass it — a firewall that doesn't
   reflect reality is documentation that lies).
4. **Variable plumbing:** deploy_public_key flows
   tfvars → prod variables.tf → module call → module variable.tf → templatefile
   → script. Public key, safe in git.
5. **Existing assets that de-risked the change:** the Elastic IP survives
   instance replacement (DEPLOY_HOST never changes); monitoring
   (Prometheus/Grafana/Loki) already self-installs at boot by downloading
   scripts from the infra repo — the fetch-and-run pattern.

## Engineering incidents in this phase

- **user_data 16KB limit exceeded:** AWS caps user_data at 16,384 bytes and
  base64 inflates content ~33%. Fix: `user_data_base64 = base64gzip(templatefile(...))`
  — cloud-init transparently gunzips. Structural alternative for future
  growth: the repo's own Section-12 pattern (slim user_data that fetches and
  runs a versioned bootstrap script — no size limit).
- **templatefile escaping:** shell `${VAR}` must be written `$${VAR}` so
  Terraform doesn't interpolate it; verified correct by base64-decoding the
  rendered payload from the plan error output.

## Status

Terraform plan validates (3 IAM resources to add; instance replacement
expected — user_data is part of instance identity). **Final apply and the
hands-off verification (a job completing via curl on a machine no human has
SSH'd into) were in progress at the time of writing** — see Planned Future
Work in the README for the acceptance test definition.
