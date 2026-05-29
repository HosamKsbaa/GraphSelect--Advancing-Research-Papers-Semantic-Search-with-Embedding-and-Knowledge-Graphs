@echo off
setlocal EnableDelayedExpansion
:: =============================================================================
::  GraphSelect — One-Click Docker Launcher (Windows)
::  Usage:
::    run_graphselect.bat           Start the application
::    run_graphselect.bat --stop    Stop and remove containers
:: =============================================================================

:: ── Constants ────────────────────────────────────────────────────────────────
set "IMAGE=ghcr.io/hosamksbaa/graphselect:latest"
set "COMPOSE_FILE=docker-compose.yml"
set "HEALTH_URL=http://localhost:8000/api/health"
set "HEALTH_TIMEOUT=30"
set "APP_URL=http://localhost:8000"
set "ENV_FILE=.env"

:: ── Banner ───────────────────────────────────────────────────────────────────
echo.
echo    ╔══════════════════════════════════════════════════════════════╗
echo    ║                                                              ║
echo    ║     ██████╗ ██████╗  █████╗ ██████╗ ██╗  ██╗                 ║
echo    ║    ██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██║  ██║                 ║
echo    ║    ██║  ███╗██████╔╝███████║██████╔╝███████║                 ║
echo    ║    ██║   ██║██╔══██╗██╔══██║██╔═══╝ ██╔══██║                 ║
echo    ║    ╚██████╔╝██║  ██║██║  ██║██║     ██║  ██║                 ║
echo    ║     ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝                 ║
echo    ║                                                              ║
echo    ║    ███████╗███████╗██╗     ███████╗ ██████╗████████╗         ║
echo    ║    ██╔════╝██╔════╝██║     ██╔════╝██╔════╝╚══██╔══╝         ║
echo    ║    ███████╗█████╗  ██║     █████╗  ██║        ██║            ║
echo    ║    ╚════██║██╔══╝  ██║     ██╔══╝  ██║        ██║            ║
echo    ║    ███████║███████╗███████╗███████╗╚██████╗   ██║            ║
echo    ║    ╚══════╝╚══════╝╚══════╝╚══════╝ ╚═════╝   ╚═╝            ║
echo    ║                                                              ║
echo    ║                   v2.3.2-beta  ·  Docker Launcher             ║
echo    ║                                                              ║
echo    ╚══════════════════════════════════════════════════════════════╝
echo.

:: ── Stop Mode ────────────────────────────────────────────────────────────────
if "%~1"=="--stop" (
    echo [INFO]  Stopping GraphSelect containers ...
    if exist "%COMPOSE_FILE%" (
        docker compose -f "%COMPOSE_FILE%" down --remove-orphans
        echo [  OK]  GraphSelect has been stopped and containers removed.
    ) else (
        echo [WARN]  No %COMPOSE_FILE% found in the current directory.
    )
    goto :eof
)

:: ── 1. Check Docker is installed ─────────────────────────────────────────────
where docker >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [FAIL]  Docker is not installed or not in PATH.
    echo.
    echo   Please install Docker Desktop for Windows:
    echo     https://docs.docker.com/desktop/install/windows-install/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('docker --version') do echo [  OK]  Docker CLI found: %%v

:: ── 2. Check Docker daemon is running ────────────────────────────────────────
docker info >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [FAIL]  Docker daemon is not running.
    echo.
    echo   Please start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)
echo [  OK]  Docker daemon is running.

:: ── 3. Gather environment variables ──────────────────────────────────────────
set "GEMINI_API_KEY="
set "OPENALEX_EMAIL="

:: Try to load existing .env file
if exist "%ENV_FILE%" (
    echo [INFO]  Found existing %ENV_FILE% — loading values ...
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        if "%%A"=="GEMINI_API_KEY" set "GEMINI_API_KEY=%%B"
        if "%%A"=="OPENALEX_EMAIL" set "OPENALEX_EMAIL=%%B"
    )
)

:: Prompt for GEMINI_API_KEY if not set
if "!GEMINI_API_KEY!"=="" (
    echo.
    echo   Enter your Gemini API key (required):
    set /p "GEMINI_API_KEY=  GEMINI_API_KEY: "
    echo.
)
if "!GEMINI_API_KEY!"=="" (
    echo [FAIL]  GEMINI_API_KEY cannot be empty.
    pause
    exit /b 1
)
echo [  OK]  GEMINI_API_KEY is set.

:: Prompt for OPENALEX_EMAIL (optional)
if "!OPENALEX_EMAIL!"=="" (
    echo.
    echo   Enter your email for OpenAlex polite pool (optional, press Enter to skip):
    set /p "OPENALEX_EMAIL=  OPENALEX_EMAIL: "
    echo.
)
if "!OPENALEX_EMAIL!"=="" (
    echo [WARN]  OPENALEX_EMAIL not set — anonymous access will be used.
) else (
    echo [  OK]  OPENALEX_EMAIL is set to: !OPENALEX_EMAIL!
)

:: ── 4. Save credentials to .env ──────────────────────────────────────────────
echo GEMINI_API_KEY=!GEMINI_API_KEY!> "%ENV_FILE%"
echo OPENALEX_EMAIL=!OPENALEX_EMAIL!>> "%ENV_FILE%"
echo [INFO]  Credentials saved to %ENV_FILE%.

:: ── 5. Generate docker-compose.yml ───────────────────────────────────────────
echo [INFO]  Generating %COMPOSE_FILE% ...
(
echo # Auto-generated by run_graphselect.bat — do not edit manually
echo version: "3.9"
echo.
echo services:
echo   graphselect:
echo     image: %IMAGE%
echo     container_name: graphselect
echo     restart: unless-stopped
echo     ports:
echo       - "8000:8000"
echo     environment:
echo       - GEMINI_API_KEY=${GEMINI_API_KEY}
echo       - OPENALEX_EMAIL=${OPENALEX_EMAIL:-}
echo     env_file:
echo       - .env
echo     healthcheck:
echo       test: ["CMD", "curl", "-f", "%HEALTH_URL%"]
echo       interval: 10s
echo       timeout: 5s
echo       retries: 3
echo       start_period: 15s
) > "%COMPOSE_FILE%"
echo [  OK]  Generated %COMPOSE_FILE%.

:: ── 6. Pull latest image and start ───────────────────────────────────────────
echo [INFO]  Pulling latest image ...
docker compose -f "%COMPOSE_FILE%" pull
echo [INFO]  Starting GraphSelect in background ...
docker compose -f "%COMPOSE_FILE%" up -d

:: ── 7. Poll health endpoint ──────────────────────────────────────────────────
echo [INFO]  Waiting for server to become healthy (timeout: %HEALTH_TIMEOUT%s) ...
set /a "elapsed=0"

:healthloop
if !elapsed! geq %HEALTH_TIMEOUT% goto :healthtimeout

:: Use PowerShell to check health endpoint silently
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo.
    echo [  OK]  Server is healthy!
    goto :healthdone
)

set /a "elapsed+=2"
echo   ... !elapsed! / %HEALTH_TIMEOUT% seconds
timeout /t 2 /nobreak >nul
goto :healthloop

:healthtimeout
echo.
echo [WARN]  Health check timed out after %HEALTH_TIMEOUT%s.
echo [WARN]  The container may still be starting — check logs with:
echo           docker compose logs -f graphselect
echo.

:healthdone

:: ── 8. Open browser ──────────────────────────────────────────────────────────
echo [INFO]  Opening browser ...
start "" "%APP_URL%"

:: ── 9. Final status ──────────────────────────────────────────────────────────
echo.
echo   ══════════════════════════════════════════════════════════════
echo     GraphSelect v2.3.2-beta is running!
echo     URL : %APP_URL%
echo   ══════════════════════════════════════════════════════════════
echo.
echo   Useful commands:
echo     * View logs   : docker compose logs -f graphselect
echo     * Stop        : run_graphselect.bat --stop
echo     * Restart     : docker compose restart graphselect
echo.

endlocal
