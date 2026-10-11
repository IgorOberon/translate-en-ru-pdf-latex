# Установка конвейера: venv + зависимости + проверка окружения.
#
#     powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# Создаёт venv рядом с собой, ставит пакеты из requirements.txt и запускает
# доктора окружения.
#
# Чего НЕ делает намеренно: не ставит Pandoc, TeX, Tesseract, LM Studio и
# MinerU. Это тяжёлые сторонние установщики со своими лицензиями и
# перезагрузками; тихо тянуть их из скрипта — плохая услуга. Доктор в конце
# назовёт, чего не хватает, и даст ссылку.
#
# Прав администратора не требует. Повторный запуск безопасен.
#
# ФАЙЛ СОХРАНЁН В UTF-8 С BOM. Без BOM Windows PowerShell 5.1 читает .ps1 как
# cp1251, и русские строки ниже становятся мусором. Правьте с сохранением BOM.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Step($text) { Write-Host "`n>> $text" -ForegroundColor Cyan }
function Bad($text)  { Write-Host "!! $text" -ForegroundColor Red }
function Good($text) { Write-Host "   $text" -ForegroundColor Green }

Write-Host "== установка конвейера ==" -ForegroundColor White
Write-Host "   папка: $root"

# Длина пути. Windows режет пути на 260 знаках, и pip падает посреди
# распаковки с «No such file or directory» на файле с длинным именем —
# сообщение при этом ни словом не поминает длину пути. Дешевле предупредить.
if ($root.Length -gt 90) {
    Write-Host ""
    Bad "путь длинный ($($root.Length) знаков)."
    Write-Host "   Windows ограничивает пути 260 знаками, и установка тяжёлых"
    Write-Host "   пакетов может упасть с невнятным «No such file or directory»."
    Write-Host "   Надёжнее держать конвейер ближе к корню диска, например D:\Конвейер."
}

# --- 1. интерпретатор -------------------------------------------------------
Step "ищу Python 3.10+"
$py = $null
foreach ($cand in @("python", "python3", "py")) {
    $exe = Get-Command $cand -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    # Заглушка Microsoft Store живёт в WindowsApps, притворяется python и
    # завершается с кодом 49, ничего не напечатав. Отсеиваем сразу.
    if ($exe.Source -like "*WindowsApps*") {
        Bad "$($exe.Source) — заглушка Microsoft Store, пропускаю"
        continue
    }
    # Версию берём из --version, а НЕ из python -c: передача кавычек в
    # нативный exe через PowerShell ломает однострочник, и проверка падает
    # на ровном месте.
    # Windows PowerShell 5.1 turns native stderr into ErrorRecord. A broken
    # candidate (or a valid --version on stderr) must not abort discovery.
    $probePreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $probeOutput = & $exe.Source --version 2>&1
        $probeCode = $LASTEXITCODE
    } catch {
        continue
    } finally {
        $ErrorActionPreference = $probePreference
    }
    if ($probeCode -ne 0) { continue }
    $out = $probeOutput -join " "
    $ver = $null
    if ($out -match 'Python\s+(\d+)\.(\d+)') { $ver = "$($Matches[1]).$($Matches[2])" }
    if ($ver -and ([version]$ver -ge [version]"3.10")) {
        $py = $exe.Source
        Good "$py  (версия $ver)"
        break
    }
}
if (-not $py) {
    Bad "не нашёл Python 3.10+ вне Microsoft Store."
    Write-Host "   Поставьте с python.org, галочка «Add python.exe to PATH», и повторите."
    exit 1
}

# --- 2. venv ----------------------------------------------------------------
$venvPy = Join-Path $root "venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    Step "venv уже есть — использую его"
} else {
    Step "создаю venv"
    & $py -m venv (Join-Path $root "venv")
    if ($LASTEXITCODE -ne 0) { Bad "не удалось создать venv"; exit 1 }
}
if (-not (Test-Path $venvPy)) { Bad "venv создан, но $venvPy нет"; exit 1 }
Good $venvPy

# --- 3. зависимости ---------------------------------------------------------
Step "обновляю pip"
& $venvPy -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Bad "pip не обновился (не смертельно, иду дальше)" }

Step "ставлю зависимости из requirements.txt"
$req = Join-Path $root "requirements.txt"
if (-not (Test-Path $req)) { Bad "нет $req"; exit 1 }
& $venvPy -m pip install -r $req
if ($LASTEXITCODE -ne 0) {
    Bad "pip install завершился с ошибкой — смотрите вывод выше."
    Write-Host "   Частая причина: нет сети или закрыт доступ к pypi.org."
    exit 1
}
Good "базовые зависимости на месте"
Write-Host "   Пакеты отдельных маршрутов (вырезание чертежей, --extract digital)"
Write-Host "   ставятся отдельно и только при надобности:"
Write-Host "       venv\Scripts\python.exe -m pip install -r requirements-extra.txt"

# --- 4. проверка ------------------------------------------------------------
Step "проверяю окружение (scripts\doctor.py)"
& $venvPy -X utf8 (Join-Path $root "scripts\doctor.py")
$code = $LASTEXITCODE

Write-Host ""
switch ($code) {
    0 { Good "Готово. Можно переводить: см. ЧИТАТЬ_ПЕРВЫМ.md" }
    2 { Write-Host "   Основное готово. Часть маршрутов недоступна — строки «ЧАСТЬ» выше." -ForegroundColor Yellow
        Write-Host "   Что доставить и как — в УСТАНОВКА.md." -ForegroundColor Yellow }
    default { Bad "Не хватает обязательного — чините строки «НЕТ» сверху вниз (УСТАНОВКА.md)." }
}
exit $code
