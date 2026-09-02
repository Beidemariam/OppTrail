$ErrorActionPreference = "Stop"
$Port = if ($env:PORT) { $env:PORT } else { "8000" }

docker build -t opptrail .
docker rm -f opptrail 2>$null
docker run `
  --name opptrail `
  --env-file .env `
  -p "${Port}:8000" `
  -v "${PWD}/data:/data" `
  opptrail
