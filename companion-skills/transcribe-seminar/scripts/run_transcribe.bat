@echo off
rem Optional wrapper that handles output redirection in one token (useful only if the user has
rem explicitly authorized a Windows scheduled task — see SKILL.md rule 2). For the normal path,
rem prefer launching transcribe.py directly via PowerShell Start-Process.
rem
rem Usage:  run_transcribe.bat "<audio>" "<outdir>"
rem (Edit the py path below if this skill lives elsewhere.)
py -3.9 -u "%~dp0transcribe.py" %1 %2 > "%~2\run.log" 2> "%~2\run.err"
