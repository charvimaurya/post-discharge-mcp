$ErrorActionPreference = 'Stop'
$main = 'C:\Users\shilp\AfterWard-A-Living-Recovery-Plan-for-Alexa'
$package = Join-Path (Split-Path $main -Parent) 'discharge-letter-check'
if (-not (Test-Path (Join-Path $main 'README.md'))) { throw "Main AfterWard repo not found at $main" }
if (-not (Test-Path (Join-Path $package '.git'))) {
  Write-Host 'Cloning the PUBLIC open-source package into a separate sibling folder...'
  git clone https://github.com/charvimaurya/discharge-letter-check.git $package
  if ($LASTEXITCODE -ne 0) { throw 'Clone failed. Check internet/Git connection.' }
}
python (Join-Path $PSScriptRoot 'apply_updates.py') --main $main --package $package
if ($LASTEXITCODE -ne 0) { throw 'Documentation patch failed; inspect console output.' }
Write-Host "`n=== Main repository changes ==="
git -C $main diff -- README.md docs/REPOSITORY_GUIDE.md
Write-Host "`n=== Open-source repository changes ==="
git -C $package diff -- README.md
Write-Host "`nChanges are LOCAL ONLY. Nothing was committed or pushed."
