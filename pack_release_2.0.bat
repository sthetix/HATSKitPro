@echo off
setlocal EnableExtensions

set "VERSION=2.0.2"
set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "RELEASE_DIR=%ROOT_DIR%\releases"
set "STAGE_DIR=%ROOT_DIR%\build\release-package\HATSKitPro"
set "OUTPUT_ZIP=%RELEASE_DIR%\HATSKitPro-%VERSION%.zip"

echo Packing HATSKit Pro %VERSION%...
echo.

if not exist "%ROOT_DIR%\HATSKitPro.exe" (
    echo ERROR: Missing HATSKitPro.exe
    echo Build or restore the launcher before packing the release.
    exit /b 1
)

if not exist "%ROOT_DIR%\hatskitpro.py" (
    echo ERROR: Missing hatskitpro.py
    exit /b 1
)

if not exist "%ROOT_DIR%\components.json" (
    echo ERROR: Missing components.json
    exit /b 1
)

if not exist "%ROOT_DIR%\src" (
    echo ERROR: Missing src folder
    exit /b 1
)

if not exist "%ROOT_DIR%\assets\component_extras" (
    echo ERROR: Missing assets\component_extras folder
    echo HATSKit Pro 2.0 packages component-owned extras instead of skeleton.zip.
    exit /b 1
)

if not exist "%RELEASE_DIR%" (
    mkdir "%RELEASE_DIR%" || exit /b 1
)

if exist "%OUTPUT_ZIP%" (
    echo Existing release ZIP found:
    echo %OUTPUT_ZIP%
    set /p "OVERWRITE=Overwrite it? [y/N]: "
    if /i not "%OVERWRITE%"=="y" (
        echo Cancelled.
        exit /b 0
    )
)

if exist "%STAGE_DIR%" (
    rmdir /s /q "%STAGE_DIR%" || exit /b 1
)

mkdir "%STAGE_DIR%" || exit /b 1

echo Copying release files...
copy /y "%ROOT_DIR%\HATSKitPro.exe" "%STAGE_DIR%\" >nul || exit /b 1
copy /y "%ROOT_DIR%\hatskitpro.py" "%STAGE_DIR%\" >nul || exit /b 1
copy /y "%ROOT_DIR%\components.json" "%STAGE_DIR%\" >nul || exit /b 1
copy /y "%ROOT_DIR%\README.md" "%STAGE_DIR%\" >nul || exit /b 1

if exist "%ROOT_DIR%\requirements.txt" (
    copy /y "%ROOT_DIR%\requirements.txt" "%STAGE_DIR%\" >nul || exit /b 1
)

robocopy "%ROOT_DIR%\src" "%STAGE_DIR%\src" /E /XD __pycache__ >nul
if errorlevel 8 exit /b 1

mkdir "%STAGE_DIR%\assets" >nul 2>&1
robocopy "%ROOT_DIR%\assets\component_extras" "%STAGE_DIR%\assets\component_extras" /E >nul
if errorlevel 8 exit /b 1

if exist "%ROOT_DIR%\image" (
    robocopy "%ROOT_DIR%\image" "%STAGE_DIR%\image" /E >nul
    if errorlevel 8 exit /b 1
)

echo Removing legacy skeleton archives from package...
del /q "%STAGE_DIR%\assets\skeleton*.zip" >nul 2>&1

if exist "%OUTPUT_ZIP%" (
    del /q "%OUTPUT_ZIP%" || exit /b 1
)

echo Creating release ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Compress-Archive -Path '%STAGE_DIR%\*' -DestinationPath '%OUTPUT_ZIP%' -Force"
if errorlevel 1 exit /b 1

echo.
echo Release package created:
echo %OUTPUT_ZIP%
echo.
echo Contents intentionally exclude assets\skeleton.zip.
echo HATSKit Pro 2.0 uses assets\component_extras as the release source of truth.

endlocal
