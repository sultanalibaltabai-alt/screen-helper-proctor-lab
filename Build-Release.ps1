$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Run-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit $LASTEXITCODE" }
}
Run-Checked python @('-m','unittest','discover','-s','screen-helper','-q')
Run-Checked node @('--test','proctor-lab/test-core.mjs','proctor-lab/test-daa.mjs','proctor-lab/test-extension.mjs','proctor-lab/test-solver.mjs','proctor-lab/test-integrity.mjs','proctor-lab/test-supervision.mjs')
Run-Checked python @('-m','unittest','discover','-s','proctor-lab/native','-q')
Push-Location -LiteralPath 'screen-helper'
try {
    Run-Checked python @('-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','ScreenHelper','--exclude-module','numpy','--distpath','dist-v2','--workpath','build-v2','--specpath','build-v2','helper.py')
    Run-Checked python @('package_release.py','8.2')
} finally { Pop-Location }
Push-Location -LiteralPath 'proctor-lab'
try {
    Run-Checked python @('-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','ProctorLabAgent','--distpath','native/dist','--workpath','native/build','--specpath','native','native/agent.py')
    Run-Checked python @('native/package_native.py')
} finally { Pop-Location }
Run-Checked python @('scripts/package_project.py')
Write-Host 'Ready: release/StudyTools-Windows-x64.zip'
