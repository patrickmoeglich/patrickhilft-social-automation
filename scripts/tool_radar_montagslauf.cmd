@echo off
REM Montagslauf des Tool-Radars, aufgerufen aus der Windows-Aufgabenplanung.
REM Zweck des Wrappers: Arbeitsverzeichnis setzen, Ausgabe mit Zeitstempel in
REM eine Logdatei haengen und den Exit-Code sichtbar machen. Ohne das laeuft der
REM Task zwar, aber ein Fehlschlag waere nirgends nachvollziehbar.

setlocal
set "REPO=%~dp0.."
set "LOG=%REPO%\logs\tool-radar.log"

REM ---------------------------------------------------------------------------
REM FREIGABEN - Spiegel des Domain-Blocks in skills\tool-radar\SKILL.md
REM
REM Headless kann keine Berechtigung erfragen: eine Rueckfrage wird still
REM abgelehnt, und der Lauf meldet die Quelle dann faelschlich als "nicht
REM erreichbar". Genau das ist am 21.08.2026 passiert - 4 von 6 Quellen fehlten.
REM
REM Bewusst hier statt in ~/.claude/settings.json: sonst duerften auch alle
REM interaktiven Sessions diese Domains ungefragt abrufen.
REM
REM >>> Wird die Quellenliste in SKILL.md geaendert, muss diese Liste mit. <<<
REM Der Test test_domains_in_skill_und_wrapper_sind_synchron schlaegt sonst an.
REM ---------------------------------------------------------------------------
set "FREIGABEN=WebSearch"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:registry.modelcontextprotocol.io)"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:github.com)"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:raw.githubusercontent.com)"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:api.github.com)"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:smithery.ai)"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:mcpservers.org)"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:code.claude.com)"
set "FREIGABEN=%FREIGABEN%,WebFetch(domain:platform.claude.com)"
REM Read/Write/Edit fuer tool-radar-gesehen.json, die beiden Bash-Muster fuer
REM die Commit-Datums-Abfrage (curl) und den Telegram-Versand (python).
set "FREIGABEN=%FREIGABEN%,Read,Write,Edit"
set "FREIGABEN=%FREIGABEN%,Bash(curl:*)"
set "FREIGABEN=%FREIGABEN%,Bash(.venv/Scripts/python.exe:*)"

if not exist "%REPO%\logs" mkdir "%REPO%\logs"

echo. >> "%LOG%"
echo ======================================================== >> "%LOG%"
echo [%DATE% %TIME%] Tool-Radar Montagslauf startet >> "%LOG%"

pushd "%REPO%"
"C:\Users\Anwender\.local\bin\claude.exe" -p "/tool-radar headless" --allowedTools "%FREIGABEN%" >> "%LOG%" 2>&1
set "CODE=%ERRORLEVEL%"
popd

if "%CODE%"=="0" (
    echo [%DATE% %TIME%] Lauf beendet, Exit-Code 0 - in Ordnung >> "%LOG%"
) else (
    echo [%DATE% %TIME%] FEHLGESCHLAGEN, Exit-Code %CODE% >> "%LOG%"
)

endlocal & exit /b %CODE%
