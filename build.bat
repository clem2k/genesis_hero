@echo off
setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

rem Set SGDK paths (local, portable - no system install needed)
set "GDK_WIN=%PROJECT_DIR%\genesis_tools\sgdk"
set "GDK=%GDK_WIN:\=/%"
set "PATH=%PROJECT_DIR%\genesis_tools\jre\bin;%PATH%"

echo =============================================
echo   Genesis Hero - Build Pipeline
echo   Guitar Hero Demake for Sega Mega Drive
echo =============================================
echo.

rem ---- Check prerequisites ----
"%PROJECT_DIR%\env\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Local Python environment not found! Please check env/
    exit /b 1
)

if not exist "%GDK_WIN%\bin\make.exe" (
    echo [ERROR] SGDK not found at %GDK_WIN%
    echo Please run: git clone --depth 1 https://github.com/Stephane-D/SGDK.git genesis_tools\sgdk
    exit /b 1
)

java -version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Java not found! SGDK rescomp requires Java 8+
    exit /b 1
)

rem ---- Build SGDK library if needed ----
if not exist "%GDK_WIN%\lib\libmd.a" (
    echo [SETUP] Compiling SGDK library ^(first time only^)...
    %GDK_WIN%\bin\make -f "%GDK_WIN%\makelib.gen"
    if errorlevel 1 (
        echo [ERROR] SGDK library compilation failed!
        exit /b 1
    )
    echo [SETUP] SGDK library compiled successfully.
    echo.
)

rem ---- Step 1: Python audio pipeline ----
echo [1/2] Processing music and generating game data...
"%PROJECT_DIR%\env\Scripts\python.exe" "%PROJECT_DIR%\tools\build_pipeline.py" "%PROJECT_DIR%" %*
if errorlevel 1 (
    echo [ERROR] Python pipeline failed!
    exit /b 1
)

rem ---- Step 2: Compile ROM ----
echo.
echo [2/2] Compiling Mega Drive ROM...
echo Debug: Running relative command: genesis_tools\sgdk\bin\make.exe -f genesis_tools\sgdk\makefile.gen
genesis_tools\sgdk\bin\make.exe -f genesis_tools\sgdk\makefile.gen
if errorlevel 1 (
    echo [ERROR] ROM compilation failed! Code: %errorlevel%
    exit /b 1
)

echo.
echo =============================================
echo   BUILD SUCCESSFUL!
echo   ROM: %PROJECT_DIR%\out\rom.bin
echo.
echo   Test with: BlastEm, Kega Fusion, or
echo   any Mega Drive emulator.
echo =============================================
endlocal
