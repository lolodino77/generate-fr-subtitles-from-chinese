<#
.SYNOPSIS
  Installation non destructive de l'environnement Conda « video_ocr », identique au PC de développement.

.DESCRIPTION
  1. Vérifie Conda et liste les environnements existants.
  2. Crée l'environnement « video_ocr » s'il n'existe pas :
       - par défaut depuis environment-lock.yml + requirements-lock.txt : versions EXACTES du PC
         de développement (Python 3.11.17, FFmpeg 9.0.2, 137 bibliothèques Python dont PyTorch CPU,
         llama-cpp-python, RapidOCR, PaddleOCR, yt-dlp…) ;
       - avec -Minimal depuis environment.yml (dépendances directes uniquement, sans PaddleOCR ni yt-dlp).
     S'il existe : l'inspecte et ne le modifie que si -Update est fourni (jamais de suppression ni de recréation).
  3. Vérifie que python/pip pointent vers video_ocr, installe le projet (python -m pip install -e .), lance pip check.
  4. Télécharge les modèles (une seule fois) dans %LOCALAPPDATA%\video_ocr\models.
  5. Lance « python -m video_ocr check ».

.PARAMETER Minimal
  Installation légère (environment.yml) au lieu de la copie exacte (environment-lock.yml).

.PARAMETER Update
  Met à jour un environnement video_ocr existant (conda env update sans --prune, puis pip install -r).

.PARAMETER UseWindowsCertStore
  Pour les PC dont l'antivirus ou le proxy inspecte le HTTPS (ex. Avast) : construit .certs\ca_bundle.pem
  (certifi + racines Windows) et l'utilise pour conda / pip / Hugging Face pendant ce script uniquement.

.PARAMETER SkipModels
  N'effectue pas le téléchargement des modèles.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -UseWindowsCertStore
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Minimal
#>
param(
    [switch]$Minimal,
    [switch]$Update,
    [switch]$UseWindowsCertStore,
    [switch]$SkipModels
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$EnvName = "video_ocr"
if ($Minimal) {
    $EnvFile = "environment.yml"; $PipReqs = @("-r", "requirements.txt", "-r", "requirements-optional.txt")
} else {
    $EnvFile = "environment-lock.yml"; $PipReqs = @("-r", "requirements-lock.txt")
}

function Step($msg) { Write-Host "`n=== $msg" -ForegroundColor Cyan }
function Check-Exit($what) { if ($LASTEXITCODE -ne 0) { throw "Échec : $what (code $LASTEXITCODE)" } }

Step "1. Vérification de Conda"
$conda = Get-Command conda -ErrorAction SilentlyContinue
if (-not $conda) { throw "Conda introuvable. Installez Miniconda/Anaconda puis relancez depuis 'Anaconda PowerShell Prompt'." }
conda --version
Write-Host "Mode : $(if ($Minimal) { 'minimal (environment.yml)' } else { 'identique au PC de développement (environment-lock.yml)' })"

if ($UseWindowsCertStore) {
    Step "Bundle de certificats (certifi + magasin Windows)"
    New-Item -ItemType Directory -Force (Join-Path $Root ".certs") | Out-Null
    $bundle = Join-Path $Root ".certs\ca_bundle.pem"
    $certifi = (& conda run -n base python -c "import certifi;print(certifi.where())").Trim()
    Get-Content $certifi -Raw | Set-Content $bundle -Encoding ascii
    foreach ($c in (Get-ChildItem Cert:\LocalMachine\Root, Cert:\CurrentUser\Root)) {
        "`n-----BEGIN CERTIFICATE-----`n" + [Convert]::ToBase64String($c.RawData, 'InsertLineBreaks') + "`n-----END CERTIFICATE-----`n" | Add-Content $bundle -Encoding ascii
    }
    $env:CONDA_SSL_VERIFY = $bundle; $env:PIP_CERT = $bundle
    $env:REQUESTS_CA_BUNDLE = $bundle; $env:SSL_CERT_FILE = $bundle
    Write-Host "Bundle : $bundle (variables définies pour cette session uniquement)"
}

Step "2. Environnements existants"
$envs = conda env list
$envs
$exists = $envs | Select-String -Pattern "^\s*$EnvName\s" -Quiet
if (-not $exists) {
    Write-Host "Création de $EnvName depuis $EnvFile (peut prendre 10 à 20 minutes)…"
    conda env create -f $EnvFile
    Check-Exit "conda env create"
} else {
    Write-Host "L'environnement $EnvName existe déjà : inspection (aucune suppression, aucune recréation)."
    conda run -n $EnvName python --version
    conda list -n $EnvName "^(python|ffmpeg)$"
    if ($Update) {
        Write-Host "Mise à jour non destructive (conda env update sans --prune)…"
        conda env update -n $EnvName -f $EnvFile
        Check-Exit "conda env update"
    } else {
        Write-Host "Pour l'aligner sur $EnvFile : relancez avec -Update."
    }
}

Step "3. Vérification de l'interpréteur, de pip et des bibliothèques"
$py = (conda run -n $EnvName python -c "import sys;print(sys.executable)").Trim()
Write-Host "python : $py"
if ($py -notmatch "[\\/]$EnvName[\\/]") { throw "L'interpréteur n'est pas celui de $EnvName : $py" }
conda run -n $EnvName python -m pip --version
if ($Update) {
    conda run --no-capture-output -n $EnvName python -m pip install @PipReqs
    Check-Exit "pip install"
}
conda run --no-capture-output -n $EnvName python -m pip install -e . --no-deps
Check-Exit "pip install -e ."
conda run --no-capture-output -n $EnvName python -m pip check

if (-not $SkipModels) {
    Step "4. Téléchargement des modèles (une seule fois, ≈ 2,5 Go ; ≈ 8 Go en mode complet)"
    $dlArgs = @("scripts\download_models.py")
    if (-not $Minimal) { $dlArgs += "--all" }
    conda run --no-capture-output -n $EnvName python @dlArgs
}

Step "5. Vérification de l'environnement"
conda run --no-capture-output -n $EnvName python -m video_ocr check
Write-Host "`nInstallation terminée." -ForegroundColor Green
Write-Host "Interface : powershell -ExecutionPolicy Bypass -File scripts\launch.ps1"
Write-Host "Tests     : powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1"
