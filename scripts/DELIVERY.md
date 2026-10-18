# Tested Aira container

This artifact contains the exact Linux/amd64 application image that passed the
commit's backend, frontend, container, and browser checks. It serves the full
UI and API from one origin.

Verify the archive and load it with Docker:

```sh
shasum -a 256 -c SHA256SUMS
docker load --input aira-linux-amd64.tar.gz
docker run --rm --platform linux/amd64 \
  -p 127.0.0.1:8000:8000 \
  -e OPENAI_API_KEY=<your-key> \
  -e AIRA_MODEL=<selected-model> \
  -v aira-data:/app/data \
  "aira:$(cat REVISION)"
```

Open http://localhost:8000. Without `OPENAI_API_KEY` and `AIRA_MODEL` the UI
still loads and uploads remain usable, but readiness reports the missing
prerequisites (503) and assessments cannot start. Readiness reflects local
configuration only and never contacts the provider; the last explicit access
check is reported separately.

To record that access check once (writes `provider-verification.json` into the
`aira-data` volume so readiness shows it):

```sh
docker run --rm --platform linux/amd64 \
  -e OPENAI_API_KEY -e AIRA_MODEL -v aira-data:/app/data \
  --entrypoint python "aira:$(cat REVISION)" -m app.llm.preflight
```

Live model access remains unverified: the API project quota was deferred, so
no live semantic evidence is claimed for this artifact. This is continuous
delivery of a tested artifact, not an AWS-hosted deployment.
Apple Silicon requires Docker's amd64 emulation, or build the source locally
with `docker compose up --build` for a native image.
