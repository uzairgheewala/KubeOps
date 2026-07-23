$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (Test-Path .\.venv\Scripts\Activate.ps1) { & .\.venv\Scripts\Activate.ps1 }
$env:PYTHONPATH = "$PWD\packages\kubeops_core;$PWD\packages\kubeops_cli;$PWD\control_plane" + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })
python -m kubeops_cli.main @args
