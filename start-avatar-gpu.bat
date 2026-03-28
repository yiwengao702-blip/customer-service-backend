@echo off
REM ============================================================
REM  Digital Human - GPU Override Launcher (Moxia / XingYun SDK)
REM
REM  MACHINE FACTS (collected 2026-10-07):
REM    Chrome              : 153.0.8010.53
REM    AMD Radeon (iGPU)   : driver 2026-05-20  (already up to date)
REM    NVIDIA RTX 3050     : driver 2022-10-31  (OUTDATED)
REM    NVIDIA Platform Ctrl: driver 2022-06-22  (OUTDATED, Optimus switching)
REM    Display output      : attached to the AMD iGPU (2560x1600)
REM    ToDesk virtual display adapter is active (remote session)
REM
REM  WHY the avatar never appears:
REM    The Moxia SDK checks WebGL2 with
REM       getContext("webgl2",{failIfMajorPerformanceCaveat:true})
REM    That flag REJECTS software rendering on purpose. With the old
REM    NVIDIA platform driver + a remote/virtual display, Chrome hands
REM    back a software (or weak) context -> SDK aborts with error
REM    10005 (INIT_ERROR) and the avatar never renders.
REM
REM  BEST FIX (do this first): update the NVIDIA drivers.
REM    - Laptop: prefer the OEM site (Lenovo / your model) or
REM      https://www.nvidia.com/drivers  (choose RTX 3050 Laptop)
REM    - Also update "NVIDIA Platform Controllers and Framework"
REM    - Afterwards, run LOCALLY (quit ToDesk) and just open
REM      http://127.0.0.1:5173 -- no script needed.
REM
REM  THIS SCRIPT = workaround while drivers are still outdated:
REM    --ignore-gpu-blocklist / --ignore-gpu-driver-blocklist
REM         accept the blocklisted 2022 drivers
REM    --use-angle=d3d11 / --use-gl=angle
REM         force the native Windows D3D11 ANGLE backend
REM    --disable-software-rasterizer
REM         make sure we do NOT silently fall back to CPU rendering
REM    --autoplay-policy=no-user-gesture-required
REM         let the digital human speak without a user gesture
REM
REM  NOTE: --enable-unsafe-swiftshader is deliberately NOT used:
REM        it only ALLOWS software rendering, which
REM        failIfMajorPerformanceCaveat rejects anyway -> still 10005.
REM
REM  IMPORTANT: close ALL Chrome windows first. Chrome reuses an
REM  existing process and then these flags silently do nothing.
REM ============================================================

set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
  echo [ERROR] Chrome not found at: %CHROME%
  pause
  exit /b 1
)

set "GPUFLAGS=--ignore-gpu-blocklist --ignore-gpu-driver-blocklist --use-angle=d3d11 --use-gl=angle --disable-software-rasterizer --autoplay-policy=no-user-gesture-required"

echo ============================================================
echo  Moxia avatar launcher - GPU override mode
echo ============================================================
echo  Root cause: NVIDIA driver 2022 + remote/virtual display.
echo  Real fix   : update NVIDIA drivers, then run locally.
echo.
echo  Close all Chrome windows first, otherwise flags are ignored.
echo.

echo [1/2] Opening WebGL diagnostic page ...
start "" "%CHROME%" %GPUFLAGS% --new-window "http://127.0.0.1:5173/webgl-diagnose.html"

echo [2/2] Opening the app ...
start "" "%CHROME%" %GPUFLAGS% --new-window "http://127.0.0.1:5173"

echo.
echo  Read the diagnostic page:
echo    - "WebGL2 (strict)" PASS -> the avatar should work now
echo    - still FAIL           -> update NVIDIA drivers, or quit
echo                             ToDesk and run locally, or switch
echo                             to the Lingmou cloud-rendering route
echo                             (lingmou-demo.html).
echo.
pause