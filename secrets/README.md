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
