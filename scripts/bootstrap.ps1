$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Push-Location ui
npm install
Pop-Location
$env:PYTHONPATH = "$PWD\packages\kubeops_core;$PWD\packages\kubeops_cli;$PWD\control_plane"
python control_plane\manage.py migrate
python control_plane\manage.py seed_release_01
python control_plane\manage.py seed_release_02
python control_plane\manage.py seed_release_04
Write-Host "KubeOps Release 0.4 is bootstrapped."
