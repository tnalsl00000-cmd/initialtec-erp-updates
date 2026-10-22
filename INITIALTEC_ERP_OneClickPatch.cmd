@echo off
chcp 65001 >nul
set "ERP_PATCH_SCRIPT=%~f0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$text=[IO.File]::ReadAllText($env:ERP_PATCH_SCRIPT,[Text.Encoding]::UTF8); $marker='#'+'__ERP_POWERSHELL__'; & ([ScriptBlock]::Create($text.Substring($text.IndexOf($marker)+$marker.Length)))"
exit /b %errorlevel%
#__ERP_POWERSHELL__
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$projectRepo='https://raw.githubusercontent.com/tnalsl00000-cmd/initialtec-erp-updates/main/'
$installDir=Join-Path $env:LOCALAPPDATA 'INITIALTEC\ERP'
$targetExe=Join-Path $installDir 'INITIALTEC_ERP.exe'
$versionFile=Join-Path $installDir 'ERP_CLIENT_VERSION.txt'
$workRoot=Join-Path ([IO.Path]::GetTempPath()) ('INITIALTEC_PATCH_'+[Guid]::NewGuid().ToString('N'))
$headers=@{'Cache-Control'='no-cache, no-store';'Pragma'='no-cache';'User-Agent'='INITIALTEC-ERP-OneClickPatch/1.0'}
$exitCode=0
function Read-Manifest {
    $stamp=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $candidates=@()
    try {$candidates+=Invoke-RestMethod -Uri ($projectRepo+'latest.json?ts='+$stamp) -Headers $headers -TimeoutSec 30} catch {Write-Host '기본 경로 확인 실패. 다른 경로를 확인합니다.' -ForegroundColor Yellow}
    try {
        $api=Invoke-RestMethod -Uri ('https://api.github.com/repos/tnalsl00000-cmd/initialtec-erp-updates/contents/latest.json?ref=main&ts='+$stamp) -Headers $headers -TimeoutSec 30
        $json=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($api.content -replace '\s',''))).TrimStart([char]0xFEFF)
        $candidates+=ConvertFrom-Json $json
    } catch {Write-Host '보조 경로 확인을 완료하지 못했습니다.' -ForegroundColor Yellow}
    $valid=@($candidates | Where-Object {$_.ok -and $_.version -match '^\d+\.\d+\.\d+$' -and $_.sha256 -match '^[a-fA-F0-9]{64}$' -and [long]$_.sizeBytes -gt 0})
    if($valid.Count -eq 0){throw '최신 패치 정보를 확인할 수 없습니다. 인터넷 연결을 확인하고 다시 실행해 주세요.'}
    return $valid | Sort-Object {[version]$_.version} -Descending | Select-Object -First 1
}
try {
    $Host.UI.RawUI.WindowTitle='INITIALTEC ERP 원클릭 최신 패치'
    Write-Host 'INITIALTEC ERP 원클릭 최신 패치' -ForegroundColor Cyan
    Write-Host '로그인 없이 최신 패치를 받아 적용합니다. 작업 중인 ERP는 닫힙니다.'
    Write-Host ''
    Write-Host '[1/6] 최신 버전 확인 중...'
    $manifest=Read-Manifest
    $expectedUrl=$projectRepo+'INITIALTEC_ERP_Update_'+$manifest.version+'.zip'
    if($manifest.packageUrl -cne $expectedUrl){throw '공식 패치 파일 경로가 아닙니다. 적용을 중단합니다.'}
    if(Test-Path -LiteralPath $versionFile){
        $current=(Get-Content -LiteralPath $versionFile -Raw).Trim()
        Write-Host ('현재 버전: '+$current)
        if($current -match '^\d+\.\d+\.\d+$' -and [version]$current -gt [version]$manifest.version){throw '설치된 버전이 공개 패치보다 높습니다. 구버전으로 덮어쓰지 않았습니다.'}
    }
    Write-Host ('받을 버전: '+$manifest.version) -ForegroundColor Green
    New-Item -ItemType Directory -Path $workRoot | Out-Null
    $zip=Join-Path $workRoot 'patch.zip'
    Write-Host '[2/6] 최신 패치 다운로드 중...'
    Invoke-WebRequest -UseBasicParsing -Uri ($expectedUrl+'?ts='+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) -Headers $headers -OutFile $zip -TimeoutSec 300
    Write-Host '[3/6] 파일 크기와 SHA256 검증 중...'
    if((Get-Item -LiteralPath $zip).Length -ne [long]$manifest.sizeBytes){throw '다운로드 파일 크기가 일치하지 않습니다. 설치하지 않았습니다.'}
    if((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ine $manifest.sha256){throw '다운로드 파일 검증에 실패했습니다. 설치하지 않았습니다.'}
    $extract=Join-Path $workRoot 'files'
    Expand-Archive -LiteralPath $zip -DestinationPath $extract
    $packageVersion=Join-Path $extract 'ERP_CLIENT_VERSION.txt'
    if(!(Test-Path -LiteralPath (Join-Path $extract 'INITIALTEC_ERP.exe')) -or !(Test-Path -LiteralPath $packageVersion)){throw '패치 안에 프로그램 또는 버전 파일이 없습니다.'}
    if((Get-Content -LiteralPath $packageVersion -Raw).Trim() -cne $manifest.version){throw '패치 내부 버전이 안내된 버전과 다릅니다. 설치하지 않았습니다.'}
    Write-Host '[4/6] 실행 중인 ERP 종료 중...'
    foreach($process in @(Get-Process -Name INITIALTEC_ERP -ErrorAction SilentlyContinue)){
        if(!$process.HasExited){
            [void]$process.CloseMainWindow()
            if(!$process.WaitForExit(3000)){$process.Kill();$process.WaitForExit(10000)}
            if(!$process.HasExited){throw 'ERP가 종료되지 않았습니다. 직접 종료한 뒤 다시 실행해 주세요.'}
        }
    }
    Write-Host '[5/6] 패치 적용 및 바로가기 연결 중...'
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    # Keep each PC's saved server address and login settings. Cloud data/cache is outside this package.
    foreach($entry in Get-ChildItem -LiteralPath $extract -Force){
        if($entry.Name -notin @('ERP_SERVER_URL.txt','login.dat')){Copy-Item -LiteralPath $entry.FullName -Destination $installDir -Recurse -Force}
    }
    $applied=(Get-Content -LiteralPath $versionFile -Raw).Trim()
    if($applied -cne $manifest.version){throw '설치 후 버전 확인에 실패했습니다.'}
    if((Get-FileHash -LiteralPath $targetExe -Algorithm SHA256).Hash -cne (Get-FileHash -LiteralPath (Join-Path $extract 'INITIALTEC_ERP.exe') -Algorithm SHA256).Hash){throw '설치 후 실행파일 확인에 실패했습니다.'}
    try {
        $shell=New-Object -ComObject WScript.Shell
        foreach($shortcutDir in @([Environment]::GetFolderPath('DesktopDirectory'),(Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'))){
            New-Item -ItemType Directory -Path $shortcutDir -Force | Out-Null
            $shortcut=$shell.CreateShortcut((Join-Path $shortcutDir 'INITIALTEC ERP.lnk'))
            $shortcut.TargetPath=$targetExe;$shortcut.WorkingDirectory=$installDir;$shortcut.IconLocation=$targetExe+',0';$shortcut.Save()
        }
    } catch {Write-Host '바로가기 갱신은 완료하지 못했습니다. 아래 설치 경로에서 실행할 수 있습니다.' -ForegroundColor Yellow}
    Write-Host ('적용 완료: v'+$applied) -ForegroundColor Green
    Write-Host ('실행 경로: '+$targetExe)
    Write-Host '[6/6] 업데이트한 ERP 실행 중...'
    Start-Process -FilePath $targetExe -WorkingDirectory $installDir
    Write-Host '로그인창의 버전 번호를 확인해 주세요.' -ForegroundColor Cyan
} catch {
    $exitCode=1
    Write-Host ''
    Write-Host ('패치 실패: '+$_.Exception.Message) -ForegroundColor Red
    Write-Host '이 화면의 오류 내용을 알려주세요. 해결 후 이 파일을 다시 실행하면 됩니다.'
} finally {
    # Only clean the exact generated temporary directory beneath the OS temporary root.
    $tempBase=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    $resolved=[IO.Path]::GetFullPath($workRoot)
    if($resolved.StartsWith($tempBase,[StringComparison]::OrdinalIgnoreCase) -and ([IO.Path]::GetFileName($resolved) -match '^INITIALTEC_PATCH_[a-f0-9]{32}$')){
        try{if(Test-Path -LiteralPath $resolved){Remove-Item -LiteralPath $resolved -Recurse -Force}}catch{}
    }
    Write-Host ''
    [void](Read-Host '엔터를 누르면 이 창을 닫습니다')
}
exit $exitCode
