# Vercel prebuilt build validation

This workflow is deliberately **build-only**. It runs manually from the `main` branch, runs the AIOS test suite, and (when Vercel credentials are configured) creates a local Vercel Build Output API artifact in GitHub Actions.

It does not deploy to Vercel, create a preview URL, assign a domain, promote a deployment, or change production.

## Why deployment is intentionally disabled

The current root `vercel.json` rewrites every request to the Railway production API:

- `/` → `https://aios-api-production-e878.up.railway.app/owner`
- `/(.*)` → `https://aios-api-production-e878.up.railway.app/$1`

A Vercel preview built from this configuration would still send its API traffic to the production Railway service. Testing task creation, approvals, agent runs, or other write-capable routes from that preview could therefore affect production data. No separate staging API origin has been verified. For that reason, this change prepares and validates the prebuilt artifact but deliberately does not upload it as a deployment.

A later deployment workflow should be added only after a separate staging backend and its persistent database are available, or after the owner explicitly approves a carefully bounded production release.

## One-time GitHub configuration

In the repository's **Settings → Secrets and variables → Actions**, configure:

| Name | Type | Value |
|---|---|---|
| `VERCEL_TOKEN` | Secret | A Vercel token created by the owner |
| `VERCEL_ORG_ID` | Variable | `team_JBZeoljERvy2CCT5AhLxvIbg` |
| `VERCEL_PROJECT_ID` | Variable | `prj_8FGQuj6Al9BGWctXHJE6mmyZGxUN` |

Enter the token directly in GitHub's secret field. Never paste it into chat, commit it, or put it in workflow YAML. If the project or team changes, verify the IDs in Vercel before updating these variables.

If these values are not configured, the test job still runs and the Vercel prebuild step is skipped safely.

## Run the validation

1. Open the repository's **Actions** tab.
2. Select **Vercel prebuilt build validation**.
3. Choose **Run workflow** on the `main` branch.
4. Wait for the Python tests and optional Vercel prebuild job.
5. If the prebuild succeeds, inspect/download the `vercel-prebuilt-<commit-sha>` artifact. It is retained for 7 days.

The Vercel CLI is pinned to `65.14.0`; GitHub Actions are pinned to reviewed commit SHAs. The Vercel build runs on the GitHub-hosted runner, not Vercel's remote build infrastructure. GitHub Actions usage and Vercel API/deployment quotas may still apply to future operations.

## Release boundary

The artifact is not a live site. No production deployment or domain change is performed by this workflow. The existing Railway service, Vercel project settings, GitHub secrets, repository visibility, and production domains are not modified by this code change.
