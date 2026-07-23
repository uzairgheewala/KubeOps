$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
& .\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD\packages\kubeops_core;$PWD\packages\kubeops_cli;$PWD\control_plane"
$api = Start-Process python -ArgumentList "control_plane\manage.py", "runserver", "0.0.0.0:8000" -PassThru
Push-Location ui
try {
  npm run dev -- --host 0.0.0.0
} finally {
  Pop-Location
  if (!$api.HasExited) { Stop-Process -Id $api.Id }
}
