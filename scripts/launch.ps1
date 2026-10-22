<#
.SYNOPSIS
  Lance l'interface locale (Streamlit) dans l'environnement Conda video_ocr.
  L'interface s'ouvre dans le navigateur à l'adresse http://localhost:8501 (accessible uniquement depuis ce PC).
  Aucun chemin propre à la machine : l'environnement est retrouvé par son nom via Conda.
.PARAMETER Headless
  Ne pas ouvrir le navigateur (utilisé par l'aperçu intégré de Claude Code, .claude/launch.json).
#>
param([int]$Port = 8501, [switch]$Headless)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:HF_HUB_OFFLINE = "1"          # aucun accès réseau nécessaire après installation
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
$headlessArg = if ($Headless) { "true" } else { "false" }
conda run --no-capture-output -n video_ocr python -m streamlit run src\video_ocr\ui\app.py `
    --server.address 127.0.0.1 --server.port $Port --server.headless $headlessArg --browser.gatherUsageStats false
