#!/usr/bin/env bash
# ============================================================
#  数字人接入 · 一键自检脚本
#  路径: D:\customer-service-backend\check-avatar.sh
#  用途: 更新显卡驱动后跑一次，确认整条链路是否已就绪。
#  说明: 内容用纯英文注释，避免 Git Bash / cmd 编码问题。
# ============================================================

echo "============================================================"
echo " Digital Human integration self-check"
echo "============================================================"

BASE="http://127.0.0.1:18082"
FRONT="http://127.0.0.1:5173"
fail=0

check() {
  # check <名称> <期望> <实际>
  if [ "$2" = "$3" ]; then
    echo "[ OK ] $1"
  else
    echo "[FAIL] $1  (expected: $2, got: $3)"
    fail=1
  fi
}

echo
echo "--- 1. backend service (18082) ---"
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$BASE/health" 2>/dev/null)
if [ "$code" = "200" ]; then
  echo "[ OK ] backend /health"
else
  echo "[FAIL] backend not responding on 18082 (http=$code)"
  fail=1
fi

echo
echo "--- 2. frontend dev server (5173) ---"
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$FRONT/" 2>/dev/null)
if [ "$code" = "200" ]; then
  echo "[ OK ] frontend 5173"
else
  echo "[FAIL] frontend not responding on 5173 (http=$code)"
  fail=1
fi

echo
echo "--- 3. digital human credentials ---"
cfg=$(curl -s -m 5 "$BASE/api/digital-human/config" 2>/dev/null)
echo "  config: $cfg"
echo "$cfg" | grep -q '"moxia_configured":true' \
  && echo "[ OK ] moxia credentials configured" \
  || echo "[WARN] moxia credentials NOT configured (check .env)"

echo "$cfg" | grep -q '"lingmou_configured":true' \
  && echo "[ OK ] lingmou credentials configured" \
  || echo "[---- ] lingmou credentials not configured (only needed for C route)"

echo
echo "--- 4. avatar session endpoint ---"
sess=$(curl -s -m 8 -w "|%{http_code}" "$BASE/api/avatar/session" 2>/dev/null)
echo "  $sess" | head -c 200; echo

echo
echo "--- 5. frontend pages reachable ---"
for p in "/" "/webgl-diagnose.html" "/lingmou-demo.html"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$FRONT$p" 2>/dev/null)
  echo "  $p -> HTTP $code"
done

echo
echo "--- 6. GPU driver dates (blocklist root cause) ---"
powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,DriverDate | Format-List" 2>/dev/null \
  | grep -Ei "Name|DriverDate" || echo "  (could not query, skip)"

echo
echo "============================================================"
if [ "$fail" = "0" ]; then
  echo " RESULT: services OK."
  echo " If the avatar still does not show, open:"
  echo "   http://127.0.0.1:5173/webgl-diagnose.html"
  echo " That page tells you whether WebGL2 strict check passed."
else
  echo " RESULT: some services are DOWN (see FAIL above)."
fi
echo "============================================================"