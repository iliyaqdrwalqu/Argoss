@echo off
:: launch.bat — Запуск ARGOS Universal OS на Windows 10/11
:: Использование: launch.bat [аргументы main.py]
:: Двойной клик или: launch.bat --full / launch.bat --no-gui
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ==========================================
echo   ARGOS UNIVERSAL OS v1.3 -- ЗАПУСК
echo ==========================================

:: 1. Найти Python (python или py)
set PYTHON=
where python >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" (
    where py >nul 2>&1 && set PYTHON=py
)
if "%PYTHON%"=="" (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 2. Проверить версию Python >= 3.10
for /f "tokens=*" %%v in ('%PYTHON% -c "import sys; print(sys.version_info >= (3,10))"') do set PYOK=%%v
if /i not "%PYOK%"=="True" (
    echo [ОШИБКА] Требуется Python 3.10+. Текущая версия:
    %PYTHON% --version
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('%PYTHON% -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")"') do set PYVER=%%v
echo   Python: %PYVER%

:: 3. Установить зависимости если нужно
%PYTHON% -c "import psutil" >nul 2>&1
if errorlevel 1 (
    echo   [SETUP] Устанавливаю зависимости...
    %PYTHON% -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ОШИБКА] Ошибка установки зависимостей. Проверь requirements.txt
        pause
        exit /b 1
    )
)

:: 4. Первая инициализация (если .env отсутствует)
if not exist ".env" (
    echo   [SETUP] Первый запуск -- инициализация...
    %PYTHON% genesis.py
)

:: 5. Создать нужные папки
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "src\skills" mkdir src\skills
if not exist "modules" mkdir modules
if not exist "tests\generated" mkdir tests\generated

:: 6. Аргументы — по умолчанию --full
set ARGS=%*
if "%ARGS%"=="" set ARGS=--full

echo   [ЗАПУСК] Запуск Аргоса (%ARGS%)...
echo ==========================================
%PYTHON% main.py %ARGS%

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Аргос завершился с ошибкой. См. logs\argos.log
    pause
)
endlocal
