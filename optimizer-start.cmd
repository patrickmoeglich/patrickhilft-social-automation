@echo off
rem Startet den Webseiten-Optimizer. Doppelklick genuegt.
cd /d "%~dp0"
chcp 65001 >nul

if "%ANTHROPIC_API_KEY%"=="" (
  echo FEHLER: ANTHROPIC_API_KEY ist nicht gesetzt.
  echo Der Schluessel ist als Benutzer-Umgebungsvariable hinterlegt ^(wie bei webgen^).
  echo Falls dieses Fenster aelter ist als die Variable: Fenster schliessen, neu oeffnen.
  pause
  exit /b 1
)

rem Abhaengigkeiten aktuell halten (beim ersten Mal 1-2 Minuten, danach Sekunden)
echo Pruefe Python-Pakete...
py -3 -m pip install -q --upgrade -r requirements.txt

set /p URL="Welche Webseite pruefen? (z.B. https://baeckerbluem.de): "
if "%URL%"=="" (
  echo Keine Adresse eingegeben.
  pause
  exit /b 1
)

py -3 scripts\website_optimizer.py %URL%
echo.
echo Fertig. Ergebnis liegt im Ordner website_optimierung\ ^(Bericht + neue Webseite^).
start "" explorer "%~dp0website_optimierung"
pause
