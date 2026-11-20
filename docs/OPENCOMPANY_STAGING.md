# Isolated OpenCompany staging

This staging target is a dedicated OpenCompany container with its own named
persistent volume. It does not use the Vercel rewrite or the legacy Railway
AIOS production service.

## Local staging

1. Copy `.env.staging.example` to `.env.staging`.
2. Generate two distinct random secrets for the owner key and credential
   encryption key. Never reuse production credentials.
3. Start the isolated API:

```bash
docker compose --env-file .env.staging -f compose.staging.yml up --build -d
```

4. Verify health and readiness:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
curl -fsS -H "X-OpenCompany-API-Key: $OPENCOMPANY_OWNER_API_KEY" http://localhost:8000/agents
```

5. Open `http://localhost:8000/owner`. Stop with
   `docker compose --env-file .env.staging -f compose.staging.yml down`.
   Do not use `down -v` unless intentionally deleting staging data.

## Isolation and limits

- The API uses a dedicated `opencompany_staging_data` Docker volume.
- Worker execution is disabled; no provider credentials are passed into the
  container and no paid or live inference is attempted.
- Use synthetic data only. Do not import production customer, supplier, or
  financial records.
- This local container is a reproducible staging package, not a hosted,
  internet-accessible staging deployment.
- A hosted environment needs a separately provisioned service, persistent
  volume, private secrets, HTTPS, backups, and an owner-approved cost review.
  Never repoint the legacy Vercel/Railway configuration at this container.
