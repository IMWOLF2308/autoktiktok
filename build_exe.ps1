param(
    [switch]$OneFile,
    [switch]$SetupOnly,
    [string]$PythonExe
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$venvPath = Join-Path $projectRoot '.venv'
$projectPython = Join-Path $venvPath 'Scripts\python.exe'
$pythonProbe = Join-Path $projectRoot 'scripts\check_build_python.py'

function Find-WorkingPython([string]$Executable, [string[]]$LauncherArgs = @()) {
    $previousErrorPreference = $ErrorActionPreference
    try {
        # A copied venv can have python.exe present but its base interpreter missing.
        # PS 5.1 turns redirected native stderr into ErrorRecords: collect them
        # without stopping the probe, and report the actual failure below.
        $ErrorActionPreference = 'Continue'
        $result = & $Executable @LauncherArgs -X utf8 $pythonProbe 2>&1
        if ($LASTEXITCODE -eq 0 -and $result) {
            return ([string]($result | Select-Object -Last 1)).Trim()
        }
        Write-Host "Python probe [$Executable $LauncherArgs]: $($result -join ' ')"
    } catch {
        Write-Host "Python probe [$Executable]: $($_.Exception.Message)"
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    return $null
}

$workingPython = Find-WorkingPython $projectPython
if (-not $workingPython) {
    Write-Host 'Moi truong .venv bi thieu/hong hoac khong tuong thich. Dang tim Python tren may nay...'
    $basePython = $null
    if ($PythonExe) {
        $basePython = Find-WorkingPython $PythonExe
        if (-not $basePython) { throw 'PythonExe khong hop le. Xem ket qua kiem tra phia tren.' }
    }
    if (-not $basePython -and (Get-Command py -ErrorAction SilentlyContinue)) {
        foreach ($version in @('-3.14', '-3.15')) {
            $basePython = Find-WorkingPython 'py' @($version)
            if ($basePython) { break }
        }
    }
    if (-not $basePython -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $basePython = Find-WorkingPython 'python'
    }
    if (-not $basePython) {
        throw 'Can Python 3.14 hoac 3.15 64-bit co Tcl/Tk. Cai Python roi chay lai lenh nay. .venv cu chua bi thay doi.'
    }

    if (Test-Path -LiteralPath $venvPath) {
        $venvItem = Get-Item -LiteralPath $venvPath -Force
        $backupPath = Join-Path $projectRoot ('.venv-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
        # Verify both absolute paths before moving; never follow a venv junction.
        if (($venvItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            $venvItem.FullName -ne $venvPath -or
            [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($backupPath)) -ne $projectRoot) {
            throw 'Duong dan .venv/backup khong an toan de tu dong di chuyen.'
        }
        Move-Item -LiteralPath $venvPath -Destination $backupPath -ErrorAction Stop
        Write-Host "Da giu nguyen moi truong cu tai: $backupPath"
    }
    Write-Host "Tao .venv bang: $basePython"
    & $basePython -m venv $venvPath
    if ($LASTEXITCODE -ne 0 -or -not (Find-WorkingPython $projectPython)) {
        throw 'Khong tao duoc .venv moi. Ban sao moi truong cu van duoc giu lai.'
    }
}

Write-Host 'Cai/kiem tra thu vien build...'
& $projectPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Khong cai duoc thu vien. Xem loi pip phia tren; kiem tra ket noi mang va quyen ghi.' }

# Reuse FFmpeg from the existing folder distribution only when no installation
# is discoverable. Copy outside dist so rebuilding dist cannot remove its input.
try {
    $ErrorActionPreference = 'Continue'
    & $projectPython -X utf8 -c 'from core.ai_reviewer import ensure_ffmpeg_available; ensure_ffmpeg_available()' 2>&1 | Out-Null
    $ffmpegAvailable = $LASTEXITCODE -eq 0
} finally {
    $ErrorActionPreference = 'Stop'
}
if (-not $ffmpegAvailable) {
    $previousBin = Join-Path $projectRoot 'dist\AutoEditTikTok\_internal\bin'
    $localBin = Join-Path $projectRoot 'bin'
    if ((Test-Path -LiteralPath (Join-Path $previousBin 'ffmpeg.exe') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $previousBin 'ffprobe.exe') -PathType Leaf)) {
        New-Item -ItemType Directory -Path $localBin -Force | Out-Null
        foreach ($tool in @('ffmpeg.exe', 'ffprobe.exe')) {
            $destination = Join-Path $localBin $tool
            if (-not (Test-Path -LiteralPath $destination)) {
                Copy-Item -LiteralPath (Join-Path $previousBin $tool) -Destination $destination -ErrorAction Stop
            }
        }
        Write-Host 'Da lay FFmpeg/FFprobe co san tu ban dist cu vao bin/.'
    }
}
& $projectPython -X utf8 build_exe.py --check-only
if ($LASTEXITCODE -ne 0) { throw 'Chua du dieu kien build. Xem loi phia tren; can FFmpeg/FFprobe trong bin/ hoac PATH.' }
& $projectPython -X utf8 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Kiem thu chua dat, dung dong goi.' }
if ($SetupOnly) {
    Write-Host 'Moi truong da san sang. SetupOnly: khong dong goi EXE.'
    return
}
if ($OneFile) { & $projectPython -X utf8 build_exe.py --onefile }
else { & $projectPython -X utf8 build_exe.py }
if ($LASTEXITCODE -ne 0) { throw 'Dong goi that bai.' }
