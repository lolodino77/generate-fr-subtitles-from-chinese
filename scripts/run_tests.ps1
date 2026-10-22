<#
.SYNOPSIS
  Exécute les tests dans l'environnement video_ocr.
.PARAMETER Fast
  Exclut les tests longs (pipeline complet) et ceux qui nécessitent les modèles de traduction.
#>
param([switch]$Fast)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:HF_HUB_OFFLINE = "1"
if ($Fast) {
    conda run --no-capture-output -n video_ocr python -m pytest -m "not slow and not models"
} else {
    conda run --no-capture-output -n video_ocr python -m pytest
}
exit $LASTEXITCODE
