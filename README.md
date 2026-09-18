# OppTrail

Timeline note-taking for sales opportunities.

## Run Locally

```bash
cp .env.example .env
./scripts/start_mac.sh
```

Open http://localhost:8000.

Set `OPENAI_API_KEY` in `.env` before using the AI sidebar. Optional:
`OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`, `ENVIRONMENT`,
and `PORT`.

Stop the container:

```bash
./scripts/stop_mac.sh
```

Linux uses `scripts/start_linux.sh` and `scripts/stop_linux.sh`. Windows
PowerShell uses `scripts/start_windows.ps1` and `scripts/stop_windows.ps1`.

## Demo Data

```bash
make seed
```

Populates the configured database with four users, five opportunities, both
share roles, an edited note, a soft-deleted note, a mention notification and
one stalled opportunity, then prints the sign-in details, what each user can
see, and a search query that returns a different result for each of them. It refuses to run on a database that already has users; pass `--force` to
add a second set.

## Development

```bash
make check-fast   # lint, types, backend and frontend tests, API contract
make check        # the full gate, including audits and Playwright E2E
make e2e          # Playwright only
make reindex      # rebuild the search index from the source tables
```

`make check` runs everything except the Docker build, the backend suite inside
the image, and the smoke test, which need a Docker socket; run those with
`make docker-test` and `make docker-smoke`. GitHub Actions
(`.github/workflows/ci.yml`) runs `make check-fast` plus both Docker steps on
push to `main` and on pull requests targeting it.
