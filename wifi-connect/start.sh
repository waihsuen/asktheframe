#!/usr/bin/env bash
set -euo pipefail

# Talk to host NetworkManager
export DBUS_SYSTEM_BUS_ADDRESS="unix:path=/host/run/dbus/system_bus_socket"

# Helper: are we online?
is_online() {
  # NM connectivity check: none/portal/limited/full
  if command -v nmcli >/dev/null 2>&1; then
    local c
    c="$(nmcli -t -f CONNECTIVITY g || echo none)"
    [[ "$c" == "full" || "$c" == "limited" ]] && return 0
  fi
  # Fallbacks: default route or quick HTTP reachability check
  ip route | grep -q '^default ' && return 0
  curl -fsS -m 10 -o /dev/null http://connectivitycheck.gstatic.com/generate_204 && return 0
  return 1
}

# Small grace period so normal auto-connect can happen first
BOOT_WAIT="${BOOT_WAIT:-10}"
sleep "$BOOT_WAIT"

# Run portal when offline; re-check later so users can reconfigure
CHECK_CONN_FREQ="${CHECK_CONN_FREQ:-120}"
while true; do
  if is_online; then
    echo "[wifi-connect] Online; not starting portal."
  else
    echo "[wifi-connect] Offline; starting captive portal…"
    if [[ -x "./wifi-connect" ]]; then
      # Env vars like PORTAL_SSID / PORTAL_PASSPHRASE are picked up automatically.
      ./wifi-connect
    else
      echo "ERROR: ./wifi-connect not found or not executable" >&2
      exit 1
    fi
  fi
  sleep "$CHECK_CONN_FREQ"
done