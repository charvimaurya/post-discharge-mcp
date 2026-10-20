# Resets Margaret's demo day: clears today's ticks and check-ins, keeps her plan.
# You do not need to stop the demo first. Run from the repository root:
#   .\scripts\reset-demo.ps1
# If Windows blocks scripts:
#   powershell -ExecutionPolicy Bypass -File .\scripts\reset-demo.ps1
# To load her plan again from the letter, upload it on /demo instead.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path ".venv\Scripts\Activate.ps1")) { Write-Error "No .venv found. Follow the Install steps in README.md first."; exit 1 }
& .\.venv\Scripts\Activate.ps1
python scripts/reset_demo_patient.py --confirm
Write-Host "Margaret's day is reset. Refresh http://127.0.0.1:3000/demo"
