# OppTrail

Timeline note-taking for sales opportunities.

## Run Locally

```bash
cp .env.example .env
./scripts/start_mac.sh
```

Open http://localhost:8000.

Set `OPENAI_API_KEY` in `.env` before using the AI sidebar. Optional:
`OPENAI_MODEL`, `ENVIRONMENT`, and `PORT`.

Stop the container:

```bash
./scripts/stop_mac.sh
```

Linux uses `scripts/start_linux.sh` and `scripts/stop_linux.sh`. Windows
PowerShell uses `scripts/start_windows.ps1` and `scripts/stop_windows.ps1`.
