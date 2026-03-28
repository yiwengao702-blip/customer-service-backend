@echo off
REM ============================================================
REM  Digital Human - Firefox launcher (Moxia / XingYun SDK)
REM
REM  WHY THIS EXISTS
REM    The Moxia SDK checks WebGL2 with
REM      getContext("webgl2",{failIfMajorPerformanceCaveat:true})
REM    On this PC (NVIDIA driver 2022 + display attached to the AMD
REM    iGPU + ToDesk virtual display) Chrome only hands back a
REM    software / degraded context, so that check fails and the SDK
REM    aborts with 10005 (INIT_ERROR).
REM
REM    Firefox exposes a preference that disables that very check:
REM      webgl.disable-fail-if-major-performance-caveat = true
REM    With it, a software-rendered WebGL2 context is accepted and
REM    the avatar renders (lower FPS, but it appears and speaks).
REM    Chrome/Edge have NO equivalent switch.
REM
REM  USAGE
REM    1) Run this script ONCE to install Firefox (skips if present)
REM    2) It then creates a dedicated profile with the preference
REM       already set, and opens the app with that profile.
REM
REM  The profile is created at:
REM    %TEMP%\moxia-avatar-profile
REM ============================================================

set "FF=%ProgramFiles%\Mozilla Firefox\firefox.exe"
if not exist "%FF%" set "FF=%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"

if not exist "%FF%" (
  echo Firefox not found. Installing via winget ...
  winget install --id Mozilla.Firefox -e --accept-source-agreements --accept-package-agreements
  set "FF=%ProgramFiles%\Mozilla Firefox\firefox.exe"
  if not exist "%FF%" set "FF=%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"
)

if not exist "%FF%" (
  echo.
  echo [ERROR] Firefox installation failed. Please install it manually:
  echo         https://www.mozilla.org/firefox/new/
  pause
  exit /b 1
)

REM --- create a dedicated profile with the required preference ---
set "PROFILE=%TEMP%\moxia-avatar-profile"
if not exist "%PROFILE%" mkdir "%PROFILE%"

set "PREFS=%PROFILE%\user.js"
if exist "%PREFS%" del "%PREFS%"

REM user.js is applied on every start: force the pref + keep WebGL on
(
  echo user_pref("webgl.disable-fail-if-major-performance-caveat", true);
  echo user_pref("webgl.force-enabled", true);
  echo user_pref("webgl.disabled", false);
  echo user_pref("gfx.webrender.all", true);
  echo user_pref("media.autoplay.default", 0);
) > "%PREFS%"

echo.
echo ============================================================
echo  Opening the app in Firefox with WebGL caveat check disabled
echo  profile: %PROFILE%
echo ============================================================

start "" "%FF%" -profile "%PROFILE%" -no-remote "http://127.0.0.1:5173"

echo.
echo  Notes:
echo   - FPS may be low because this falls back to software rendering.
echo   - For BEST performance, still update the NVIDIA drivers.
echo   - Alternative: Lingmou cloud rendering (no GPU needed):
echo     http://127.0.0.1:5173/lingmou-demo.html
echo.
pause