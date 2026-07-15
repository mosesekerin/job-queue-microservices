# Repository Assets

## Diagrams included in the docs (ASCII, render-anywhere)
- System/data-flow diagram — docs/architecture.md
- Pipeline gate chain — docs/ci-pipeline.md
- Preparation-vs-deployment worlds map — recommended addition from the
  project's working notes (two-worlds mind map)

## Recommended screenshots (capture these; they exist in the project history)
1. GitHub Actions run with all six jobs green and the needs: chain visible
   (Actions → latest main run → graph view).
2. A deliberately red run (e.g., the flake8 failure or a Trivy CRITICAL) —
   evidence the gates actually gate.
3. Trivy report table showing the gnutls CRITICALs with Status=fixed
   (before the apt-upgrade fix) and a clean run after.
4. `docker compose ps` with all four services `(healthy)` on the server,
   frontend showing `0.0.0.0:3001->3000/tcp`.
5. The restart-policy fingerprint: worker with CREATED "about an hour ago"
   and STATUS "Up 2 minutes" after the production TimeoutError crash.
6. Coverage artifact attached to a run summary.
7. Rolling deploy mid-flight: `docker compose ps` showing two api containers
   coexisting during --scale api=2.
8. terraform plan output: 3 IAM resources to add + instance replacement.

## Suggested additional visuals (to author)
- Sequence diagram of one job (browser → frontend → api → redis → worker →
  redis → api → browser), e.g., Mermaid `sequenceDiagram`.
- Deployment diagram: GitHub runner → SSH → EC2 (EIP) → compose stack, with
  the three-secrets boundary marked.
- Rolling-update state diagram: old-serving → both-running → verified →
  cutover / abort.
