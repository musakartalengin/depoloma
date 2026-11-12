# Depoloma installer for Windows.
#
#   irm https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.ps1 | iex
#
# Downloads Depoloma into %LOCALAPPDATA%\Programs\Depoloma and adds Desktop + Start Menu
# shortcuts. Nothing needs administrator rights. Running it again updates Depoloma.
# To remove it again:
#
#   powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\Depoloma\install.ps1" -Uninstall
#
# The program lives apart from its clean-up log (%LOCALAPPDATA%\Depoloma), so updating
# or removing the program never loses the record of past clean-ups.
param(
    [string]$Repo = "musakartalengin/depoloma",
    [string]$Branch = "main",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"            # the progress bar makes Invoke-WebRequest very slow on PowerShell 5
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
$dest = Join-Path $env:LOCALAPPDATA "Programs\Depoloma"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Depoloma.lnk"
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Depoloma.lnk"

if ($Uninstall) {
    foreach ($p in @($desktop, $startMenu)) { if (Test-Path $p) { Remove-Item $p -Force } }
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Write-Host "Depoloma kaldirildi (removed). Temizlik kaydi yerinde kaldi (clean-up log kept): $env:LOCALAPPDATA\Depoloma"
    return
}

function Find-Python {
    foreach ($cand in @(@("py", "-3"), @("python"), @("python3"))) {
        $exe = $cand[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $extra = @()
        if ($cand.Count -gt 1) { $extra = $cand[1..($cand.Count - 1)] }
        try {
            $path = & $exe @extra -c "import sys; assert sys.version_info >= (3, 8); print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $path) { return $path.Trim() }
        } catch { }
    }
    return $null
}

Write-Host "Depoloma indiriliyor (downloading)..."
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("depoloma-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $zip = Join-Path $tmp "depoloma.zip"
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $tmp
    $src = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
    if (-not $src) { throw "Download did not contain the project folder." }
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }      # replaces a previous Depoloma install only
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Move-Item -Path $src.FullName -Destination $dest
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

$python = Find-Python
if (-not $python) {
    Write-Host ""
    Write-Host "Python 3.8+ bulunamadi (not found)."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $answer = Read-Host "Python simdi kurulsun mu? Install it now with winget? [E/y = evet/yes]"
        if ($answer -match "^[EeYy]") {
            winget install -e --id Python.Python.3.12 --scope user
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
            $python = Find-Python
        }
    }
}

$shell = New-Object -ComObject WScript.Shell
foreach ($lnk in @($desktop, $startMenu)) {
    $s = $shell.CreateShortcut($lnk)
    if ($python) {
        $pythonw = Join-Path (Split-Path $python) "pythonw.exe"
        if (Test-Path $pythonw) { $s.TargetPath = $pythonw } else { $s.TargetPath = $python }
        $s.Arguments = "-m depoloma"
    } else {
        $s.TargetPath = Join-Path $dest "Depoloma.bat"
    }
    $s.WorkingDirectory = $dest
    $s.IconLocation = (Join-Path $dest "depoloma\web\icon.ico")
    $s.Description = "Depoloma - disk alanin nereye gitti?"
    $s.Save()
}

Write-Host ""
Write-Host "Depoloma kuruldu (installed): $dest"
Write-Host "Masaustundeki 'Depoloma' kisayoluna cift tiklayin. Double-click the 'Depoloma' shortcut on your desktop."
if (-not $python) { Write-Host "Not: once Python kurulmali (Python must be installed first): https://www.python.org/downloads/" }
