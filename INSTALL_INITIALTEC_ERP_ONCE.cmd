@echo off
setlocal
set "SELF=%~f0"
title INITIALTEC ERP - One Time Installer
echo ============================================================
echo  INITIALTEC ERP - ONE TIME INSTALLER
echo ============================================================
echo.
echo Downloading the latest verified Firebase ERP build...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-Content -LiteralPath $env:SELF -Raw; $m='###POWERSHELL###'; $i=$c.IndexOf($m); if($i -lt 0){throw 'Installer payload not found.'}; Invoke-Expression ($c.Substring($i+$m.Length))"
set "EC=%ERRORLEVEL%"
echo.
if not "%EC%"=="0" (
  echo INSTALL FAILED. Error code: %EC%
  echo Please send this screen to ChatGPT.
) else (
  echo INSTALL COMPLETE.
  echo From now on, launch INITIALTEC ERP from the desktop shortcut.
)
echo.
pause
exit /b %EC%
###POWERSHELL###
$ErrorActionPreference='Stop'
$manifestUrl='https://raw.githubusercontent.com/tnalsl00000-cmd/initialtec-erp-updates/main/latest.json'
$installDir=Join-Path $env:LOCALAPPDATA 'INITIALTEC\ERP'
$tempRoot=Join-Path $env:TEMP ('INITIALTEC_BOOTSTRAP_'+[Guid]::NewGuid().ToString('N'))
$zipPath=Join-Path $tempRoot 'INITIALTEC_ERP_Update.zip'
$extractDir=Join-Path $tempRoot 'extract'

try {
    New-Item -ItemType Directory -Force -Path $tempRoot,$extractDir | Out-Null
    Write-Host '[1/6] Reading update manifest...'
    $meta=Invoke-RestMethod -Uri $manifestUrl -Method Get -TimeoutSec 30
    if(-not $meta.ok){throw 'Update manifest is not ready.'}
    if([string]::IsNullOrWhiteSpace([string]$meta.packageUrl)){throw 'Update package URL is empty.'}
    Write-Host ('      Version: '+[string]$meta.version)

    Write-Host '[2/6] Downloading package...'
    Invoke-WebRequest -Uri ([string]$meta.packageUrl) -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
    if(-not (Test-Path -LiteralPath $zipPath)){throw 'Update package was not downloaded.'}

    Write-Host '[3/6] Verifying SHA256...'
    $actual=(Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
    $expected=([string]$meta.sha256).Trim().ToUpperInvariant()
    if(-not [string]::IsNullOrWhiteSpace($expected) -and $actual -ne $expected){
        throw ('SHA256 mismatch. expected='+$expected+' actual='+$actual)
    }
    Write-Host '      SHA256 OK'

    Write-Host '[4/6] Extracting and installing...'
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $newExe=Join-Path $extractDir 'INITIALTEC_ERP.exe'
    if(-not (Test-Path -LiteralPath $newExe)){throw 'INITIALTEC_ERP.exe is missing from the package.'}

    Get-Process INITIALTEC_ERP -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 700
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    Get-ChildItem -LiteralPath $extractDir -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $installDir -Recurse -Force
    }

    Write-Host '[5/6] Creating shortcuts...'
    $exe=Join-Path $installDir 'INITIALTEC_ERP.exe'
    $wsh=New-Object -ComObject WScript.Shell
    $desktop=[Environment]::GetFolderPath('Desktop')
    $lnk=$wsh.CreateShortcut((Join-Path $desktop 'INITIALTEC ERP.lnk'))
    $lnk.TargetPath=$exe
    $lnk.WorkingDirectory=$installDir
    $lnk.Description='INITIALTEC ERP - Firebase Cloud'
    $lnk.Save()

    $programs=Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'
    New-Item -ItemType Directory -Force -Path $programs | Out-Null
    $lnk2=$wsh.CreateShortcut((Join-Path $programs 'INITIALTEC ERP.lnk'))
    $lnk2.TargetPath=$exe
    $lnk2.WorkingDirectory=$installDir
    $lnk2.Description='INITIALTEC ERP - Firebase Cloud'
    $lnk2.Save()

    Write-Host '[6/6] Starting ERP...'
    Start-Process -FilePath $exe -WorkingDirectory $installDir
    Write-Host ''
    Write-Host ('Installed version '+[string]$meta.version+' successfully.') -ForegroundColor Green
    Write-Host ('Install path: '+$installDir) -ForegroundColor Green
}
finally {
    try { if(Test-Path -LiteralPath $tempRoot){Remove-Item -LiteralPath $tempRoot -Recurse -Force} } catch {}
}
