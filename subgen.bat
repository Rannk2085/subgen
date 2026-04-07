@echo off
REM subgen launcher (Windows)
setlocal

set "DIR=%~dp0"

REM 检测 Python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=python"
) else (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON=py"
    ) else (
        echo ERROR: Python 未安装
        echo   一键安装: winget install Python.Python.3.12
        exit /b 1
    )
)

REM 检查版本 ^>= 3.11
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: 需要 Python 3.11 或更新版本
    %PYTHON% --version
    exit /b 1
)

%PYTHON% -B "%DIR%src\main.py" %*
endlocal
