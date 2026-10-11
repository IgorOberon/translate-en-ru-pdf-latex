# env_doctor.ps1 - one-shot health check for a Python/ML environment on Windows.
# Runs the checks from windows-python-env/SKILL.md and prints an OK/FAIL line
# per check with a cure. Read-only: changes nothing.
#
# NOTE: this file is deliberately pure ASCII - PowerShell 5.1 reads BOM-less
# scripts as ANSI, and any typographic dash/quote would corrupt the parse.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\env_doctor.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\env_doctor.ps1 --help

if ($args -contains '--help' -or $args -contains '-h' -or $args -contains '/?') {
    Write-Host @'
env_doctor.ps1 - diagnose the classic Windows Python/ML traps (read-only).

Checks:
  venv        (venv) active and first on PATH
  python      where.exe python: real interpreter, not the Store stub
  launcher    py launcher available as fallback
  torch       torch imports and torch.cuda.is_available() (skipped if no torch)
  HF_HOME     model cache relocated off a Cyrillic/space profile path
  ExecPolicy  Activate.ps1 not blocked by ExecutionPolicy
  console     output encoding is UTF-8 (mojibake guard)

Exit code = number of FAIL rows. WARN rows do not affect it.
'@
    exit 0
}

$script:ok = 0; $script:warn = 0; $script:fail = 0
function Show-Row($status, $check, $detail, $cure) {
    switch ($status) {
        'OK'   { $script:ok++ }
        'WARN' { $script:warn++ }
        'FAIL' { $script:fail++ }
    }
    Write-Host ("[{0,-4}] {1,-10} {2}" -f $status, $check, $detail)
    if ($cure) { Write-Host ("       {0,-10} cure: {1}" -f '', $cure) }
}

# --- venv marker --------------------------------------------------------------
if ($env:VIRTUAL_ENV) {
    Show-Row 'OK' 'venv' "active: $env:VIRTUAL_ENV"
} elseif ($env:CONDA_DEFAULT_ENV) {
    Show-Row 'WARN' 'venv' "conda env ($env:CONDA_DEFAULT_ENV) hijacked the shell, no project venv" 'activate the project venv ON TOP: .\venv\Scripts\Activate.ps1'
} else {
    Show-Row 'FAIL' 'venv' 'no (venv) in this shell' 'py -3.12 -m venv venv; .\venv\Scripts\Activate.ps1 (every new window!)'
}

# --- where.exe python: Store stub / order --------------------------------------
$pythons = @(where.exe python 2>$null)
$firstReal = $null
if (-not $pythons) {
    Show-Row 'FAIL' 'python' 'no python on PATH' 'install from python.org (Add to PATH) or use the py launcher'
} else {
    $first = $pythons[0]
    if ($first -like '*\WindowsApps\*') {
        Show-Row 'FAIL' 'python' "first hit is the Store stub: $first" 'use py -3.x or venv\Scripts\python.exe; or disable App execution aliases'
    } elseif ($env:VIRTUAL_ENV -and $first -notlike "$env:VIRTUAL_ENV*") {
        Show-Row 'FAIL' 'python' "venv active but first python is $first" 're-activate the venv; its Scripts dir must be FIRST on PATH'
    } else {
        $firstReal = $first
        $v = & $first --version
        Show-Row 'OK' 'python' "$first ($v)"
    }
}

# --- py launcher ----------------------------------------------------------------
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    Show-Row 'OK' 'launcher' "py launcher at $($py.Source)"
} else {
    Show-Row 'WARN' 'launcher' 'py launcher not found' 'reinstall Python from python.org with the launcher option ticked'
}

# --- torch + CUDA ----------------------------------------------------------------
$pyExe = $null
if ($env:VIRTUAL_ENV -and (Test-Path "$env:VIRTUAL_ENV\Scripts\python.exe")) { $pyExe = "$env:VIRTUAL_ENV\Scripts\python.exe" }
elseif ($firstReal) { $pyExe = $firstReal }
elseif ($py) { $pyExe = 'py' }
if ($pyExe) {
    $torchOut = & $pyExe -c "import torch; print(torch.__version__, torch.cuda.is_available())" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Show-Row 'WARN' 'torch' "torch not importable via $pyExe" 'only needed for GPU tools; pip install torch --index-url https://download.pytorch.org/whl/cu128'
    } elseif ("$torchOut" -match 'True') {
        Show-Row 'OK' 'torch' "$torchOut (CUDA available)"
    } else {
        Show-Row 'FAIL' 'torch' "CPU build or no CUDA: $torchOut" 'pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --force-reinstall (cu121/cu124 for RTX 30/40)'
    }
} else {
    Show-Row 'WARN' 'torch' 'skipped: no usable python found' 'fix the python row first'
}

# --- HF_HOME / Cyrillic profile ----------------------------------------------------
$profileNonAscii = $env:USERPROFILE -match '[^\x00-\x7F]'
if ($env:HF_HOME) {
    if ($env:HF_HOME -match '[^\x00-\x7F]|\s') {
        Show-Row 'FAIL' 'HF_HOME' "set, but path has non-ASCII/spaces: $env:HF_HOME" 'point it to a latin path: [Environment]::SetEnvironmentVariable() + $env:HF_HOME, see SKILL.md'
    } else {
        Show-Row 'OK' 'HF_HOME' $env:HF_HOME
    }
} elseif ($profileNonAscii) {
    Show-Row 'FAIL' 'HF_HOME' "not set and profile is non-ASCII ($env:USERPROFILE), caches will land there" 'set User-level HF_HOME to a latin path AND $env:HF_HOME for this window (SKILL.md, Cyrillic paths)'
} else {
    Show-Row 'OK' 'HF_HOME' 'not set; ASCII profile path, default cache is safe'
}

# --- ExecutionPolicy -----------------------------------------------------------------
$ep = Get-ExecutionPolicy -Scope CurrentUser
$epEff = Get-ExecutionPolicy
if ($epEff -eq 'Restricted' -or $epEff -eq 'AllSigned') {
    Show-Row 'FAIL' 'ExecPolicy' "effective policy $epEff blocks Activate.ps1" 'Set-ExecutionPolicy -Scope CurrentUser RemoteSigned (once)'
} else {
    Show-Row 'OK' 'ExecPolicy' "effective: $epEff (CurrentUser: $ep)"
}

# --- console encoding (mojibake guard) -------------------------------------------------
$cp = [Console]::OutputEncoding.CodePage
if ($cp -eq 65001) {
    Show-Row 'OK' 'console' 'output encoding UTF-8 (65001)'
} else {
    Show-Row 'WARN' 'console' "output codepage $cp, Russian UTF-8 text will show as mojibake" 'chcp 65001 or [Console]::OutputEncoding=[Text.Encoding]::UTF8'
}

Write-Host ''
Write-Host ("{0} OK, {1} WARN, {2} FAIL" -f $script:ok, $script:warn, $script:fail)
exit $script:fail
