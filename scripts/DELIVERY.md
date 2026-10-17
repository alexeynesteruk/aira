# Tested Aira container

This artifact contains the exact Linux/amd64 application image that passed the
commit's backend, frontend, container, and browser checks. It currently serves
the application shell. Assessment processing is not implemented yet.

Verify the archive and load it with Docker:

```sh
shasum -a 256 -c SHA256SUMS
docker load --input aira-linux-amd64.tar.gz
docker run --rm --platform linux/amd64 -p 127.0.0.1:8000:8000 "aira:$(cat REVISION)"
```

Open http://localhost:8000. Liveness returns 200; assessment readiness returns
503 until the assessment workflow is implemented and configured. This is
continuous delivery of a tested artifact, not an AWS-hosted deployment.
Apple Silicon requires Docker's amd64 emulation, or build the source locally
with `docker compose up --build` for a native image.
