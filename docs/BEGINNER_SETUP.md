# Beginner setup guide

This guide is for the independent OpenCompany AIOS application in this repository. It does not deploy the application or connect external business accounts.

## What you need

- A computer with Python 3.11 or newer for local development. An Android phone can view GitHub and use a hosted owner console, but it is not a supported environment for running this Python server locally.
- Access to this repository and permission to install its dependencies.
- Two separate random secrets: an owner API key and an encryption key of at least 32 characters.
- A persistent database location for any hosted environment.

There is no guarantee that a hosted provider, model provider or integration remains free. Keep paid services disabled and check current pricing and terms before connecting anything.

## Run locally

1. Clone the repository and switch to the reviewed development branch. Do not use main or the legacy src/ai_os package as the new application runtime.
2. Create and activate a Python virtual environment.
3. Install the project and development dependencies.
4. Set the required environment variables in your local shell or an untracked .env file. Never paste real secrets into GitHub, source files, screenshots or chat.
5. Keep all worker and automation switches disabled for the first startup.
6. Start the API and open the owner console.

Example commands on macOS/Linux:

```bash
git clone https://github.com/hamza00alik-source/ai-operating-system.git
cd ai-operating-system
git switch feature/storefront-adapter-foundation
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export OPENCOMPANY_OWNER_API_KEY="replace-with-a-long-random-secret"
export OPENCOMPANY_SECRET_ENCRYPTION_KEY="replace-with-a-separate-random-secret-of-at-least-32-characters"
export OPENCOMPANY_COOKIE_SECURE="false"
export OPENCOMPANY_WORKER_AUTOSTART="false"
python main.py
```

Open http://127.0.0.1:8000/owner. Use http://127.0.0.1:8000/docs for the API reference. Local HTTP is for isolated development only; hosted environments must use HTTPS and OPENCOMPANY_COOKIE_SECURE=true.

Windows users should activate the environment with .venv\\Scripts\\activate and set environment variables using PowerShell syntax.

## First safe checks

1. Sign in to the owner console.
2. Confirm the database is persistent and the owner-only diagnostics are accessible.
3. Check /audit/verify and confirm the audit chain is valid.
4. Download an owner backup and keep it somewhere protected.
5. Run the automated test suite with pytest.
6. Keep the worker fleet stopped until the owner has reviewed the workforce, verified a genuinely zero-cost model provider and explicitly approved the test.

## Connecting a model provider

A model name ending in :free is not sufficient proof of zero cost. Confirm the provider's current pricing, account eligibility, privacy terms and business-use rights. Add credentials only through the encrypted provider configuration path. Use synthetic non-sensitive test prompts first. Never enable a paid fallback.

## Connecting WooCommerce

Use a dedicated WooCommerce REST API key with Read permission only. Select the correct business unit, save credentials through the authenticated owner console, then explicitly test the connection. Saving credentials alone does not test the store. The current adapter reads products, orders and WooCommerce-recorded payment-status signals; it does not publish products, change orders, issue refunds, fulfil orders or verify bank settlement.

## Current operating boundaries

- Product & R&D automation and manager proposals default OFF.
- Worker autostart defaults OFF and requires a successful owner provider test.
- External marketplace channels remain disconnected and unverified.
- Payout reconciliation is a preview against owner-supplied ledger references, not proof of settlement.
- Approval records do not execute external actions.
- No merge to main, production deployment, purchase, payment, payout, listing publication or customer commitment is authorized by following this guide.

For backup handling and recovery, see docs/PRODUCTION_OPERATIONS_RUNBOOK.md. For the implementation status and remaining gates, see docs/ROADMAP.md.