# Runtime secrets

Files in this directory are mounted read-only into runtime containers and are
ignored by Git. For a future RTSP deployment, create `secrets/rtsp_url` locally
with the complete camera URL and restrict it to the current user:

```bash
mkdir -p secrets
chmod 700 secrets
printf '%s' 'rtsp://username:password@camera-host:554/stream' > secrets/rtsp_url
chmod 600 secrets/rtsp_url
```

Do not commit, paste into logs, or place real credentials in an example file.

Production authentication also expects:

- `secrets/admin_password`: initial Admin password (minimum 12 characters).
- `secrets/ingest_token`: a high-entropy token used only by the AI ingestion service.

After the first Admin is created in the persistent database, remove the
bootstrap username from the environment and remove `admin_password` from the
host. Keep `ingest_token` available to the Backend and AI worker through the
deployment secret manager.
