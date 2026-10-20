# Starts the AfterWard demo: MCP server, bridge and web app, plus the Alexa tunnel if asked.
# Run from the repository root (if Windows blocks scripts, put
# "powershell -ExecutionPolicy Bypass -File" in front):
#
#   .\scripts\start-demo.ps1                  start the web demo
#   .\scripts\start-demo.ps1 -Alexa           also start the Cloudflare tunnel for the Alexa skill
#   .\scripts\start-demo.ps1 -Reset           reset Margaret's day first, then start
#   .\scripts\start-demo.ps1 -Reset -Alexa    reset, then start everything
#   .\scripts\start-demo.ps1 -Record -Reset -Alexa
#                                             for a recording take: also fixes the demo clock
#                                             to 23 Oct, 07:00 (does not change .env)
#   .\scripts\start-demo.ps1 -CloudMcp        OPTIONAL: use the MCP server on AWS (ECS) instead
#                                             of a local copy. See docs/mcp-on-aws.md first.
#
# Already running and only want a fresh day? Run .\scripts\reset-demo.ps1
# or press "Reset demo" on /demo. Reset keeps her plan; to reload the plan, upload the letter again.
# To stop, close the windows. After changing .env, close all windows and run this again.
param([switch]$Alexa, [switch]$Reset, [switch]$Record, [switch]$CloudMcp)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Stop early with a clear message if setup is missing.
if (-not (Test-Path ".venv\Scripts\Activate.ps1")) { Write-Error "No .venv found. Follow the Install steps in README.md first."; exit 1 }
if (-not (Test-Path ".env")) { Write-Error "No .env found. Copy .env.example to .env and fill it in."; exit 1 }

$activate = ".\.venv\Scripts\Activate.ps1"

# Settings for this run only. They are set inside this script's own process, so every
# window it opens inherits them and they win over .env. Your terminal and .env are unchanged.
# By default the bridge talks to the local MCP server started below (today's code).
# With -CloudMcp it talks to the MCP server on AWS instead.
$cloudMcpUrl = "https://dakpc9juquqks.cloudfront.net/mcp"
if ($CloudMcp) {
  $env:MCP_URL = $cloudMcpUrl
  # The cloud server checks a token kept in AWS Secrets Manager. Read it for this run only.
  $env:MCP_AUTH_TOKEN = & .\.venv\Scripts\python.exe -c "import boto3; print(boto3.client('secretsmanager', region_name='eu-west-2').get_secret_value(SecretId='afterward/mcp/auth-token')['SecretString'].strip())"
  if (-not $env:MCP_AUTH_TOKEN) { Write-Error "Could not read the MCP token from Secrets Manager (secret afterward/mcp/auth-token). Check your AWS access, or run without -CloudMcp."; exit 1 }
  Write-Host "Cloud MCP: the bridge uses $cloudMcpUrl" -ForegroundColor Cyan
  Write-Host "It runs the code from the last ECS deploy, and its clock comes from the ECS task settings." -ForegroundColor Cyan
} else {
  $env:MCP_URL = "http://127.0.0.1:8001/mcp"
}
$env:ALEXA_FEED_ENABLED = "true"   # show Alexa turns on /demo
$env:PYTHONUNBUFFERED = "1"        # log lines appear straight away
if ($Record) {
  $env:CLOCK_MODE = "demo"
  $env:DEMO_FIXED_NOW = "2026-10-23T07:00:00+01:00"
  Write-Host "Recording mode: demo clock fixed to 23 Oct 2026, 07:00 UK time."
}

# Opens one part in its own PowerShell window, titled so you can tell them apart.
function Start-Part($title, $cmd) {
  Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
    "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location '$root'; $cmd"
}

if ($Reset) { & $activate; python scripts/reset_demo_patient.py --confirm }

if (-not $CloudMcp) {
  Start-Part "1 MCP server :8001" "$activate; python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001"
  Start-Sleep -Seconds 3   # let the MCP server start before the bridge connects to it
}
Start-Part "2 Bridge :8002"     "$activate; python scripts/run_web_bridge.py --port 8002"
Start-Part "3 Web app :3000"    "cd web; npm run dev"
if ($Alexa) {
  # Start the tunnel with a log file, so this script can read its new address.
  $tunnelLog = Join-Path $env:TEMP "afterward-tunnel.log"
  Remove-Item $tunnelLog -ErrorAction SilentlyContinue
  Start-Part "4 Tunnel" "cloudflared tunnel --url http://127.0.0.1:8002 --logfile '$tunnelLog'"
  Write-Host "Waiting for the tunnel address..."
  $tunnelUrl = $null
  foreach ($i in 1..45) {
    Start-Sleep -Seconds 1
    if (Test-Path $tunnelLog) {
      # Skip Cloudflare's own api.trycloudflare.com address; keep the tunnel's address.
      $found = Select-String -Path $tunnelLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches |
        ForEach-Object { $_.Matches.Value } | Where-Object { $_ -ne 'https://api.trycloudflare.com' } | Select-Object -First 1
      if ($found) { $tunnelUrl = $found; break }
    }
  }
}

Write-Host "MCP_URL=$env:MCP_URL  CLOCK_MODE=$(if ($env:CLOCK_MODE) { $env:CLOCK_MODE } else { 'from .env' })"
Write-Host "Open http://127.0.0.1:3000/demo"
if ($Alexa) {
  if ($tunnelUrl) {
    $endpoint = "$tunnelUrl/alexa"
    Set-Clipboard -Value $endpoint
    Write-Host ""
    Write-Host "Alexa endpoint (copied to your clipboard):" -ForegroundColor Green
    Write-Host "  $endpoint" -ForegroundColor Green
  } else {
    Write-Host "Could not read the tunnel address. Copy the https://...trycloudflare.com address" -ForegroundColor Yellow
    Write-Host "from the Tunnel window and add /alexa on the end." -ForegroundColor Yellow
  }
  Write-Host "In the Alexa console: open the skill > Build > Endpoint > HTTPS."
  Write-Host "Paste it in Default Region, choose the wildcard-certificate option, then click Save Endpoints."
  Start-Process "https://developer.amazon.com/alexa/console/ask"
}
