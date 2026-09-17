#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AI_DIR="$ROOT_DIR/ai"
PYTHON="$AI_DIR/.venv/bin/python"
CONFIG="$AI_DIR/config/live_camera.json"
RUNTIME_DIR="$AI_DIR/live_output/.runtime"
LAUNCHD_DIR="$ROOT_DIR/scripts/launchd"
LAUNCH_DOMAIN="gui/$(id -u)"

CAMERA_IDS=("camera-3" "camera-5" "camera-7")
CAMERA_NAMES=("DVR Camera 3" "DVR Camera 5" "DVR Camera 7")
CAMERA_URL_VARS=("CITYEYE_RTSP_CAMERA_3_URL" "CITYEYE_RTSP_CAMERA_5_URL" "CITYEYE_RTSP_CAMERA_7_URL")
CAMERA_DEFAULT_URLS=(
  "rtsp://192.168.1.10:554/live_ch02_0"
  "rtsp://192.168.1.10:554/live_ch04_0"
  "rtsp://192.168.1.10:554/live_ch06_0"
)
ENABLED_CAMERA_IDS="${CITYEYE_ENABLED_CAMERA_IDS:-camera-3}"

camera_is_enabled() {
  local camera_id="$1"
  [[ ",${ENABLED_CAMERA_IDS// /}," == *",$camera_id,"* ]]
}

mkdir -p "$RUNTIME_DIR"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

find_worker_pid() {
  local camera_id="$1"
  pgrep -f "[p]rocess_video.py.*--camera-id ${camera_id}" | head -1 || true
}

start_workers() {
  if [[ ! -x "$PYTHON" ]]; then
    echo "Missing AI virtual environment: $PYTHON" >&2
    exit 1
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "Missing local live-camera config: $CONFIG" >&2
    exit 1
  fi

  cd "$AI_DIR"
  for index in 0 1 2; do
    local camera_id="${CAMERA_IDS[$index]}"
    local camera_name="${CAMERA_NAMES[$index]}"
    local url_variable="${CAMERA_URL_VARS[$index]}"
    local default_url="${CAMERA_DEFAULT_URLS[$index]}"
    local stream_url="${!url_variable:-$default_url}"
    local output_dir="$AI_DIR/live_output/$camera_id"
    local pid_file="$RUNTIME_DIR/$camera_id.pid"

    if ! camera_is_enabled "$camera_id"; then
      echo "Skipping $camera_name (disabled; CITYEYE_ENABLED_CAMERA_IDS=$ENABLED_CAMERA_IDS)"
      continue
    fi

    if [[ "$(uname -s)" == "Darwin" ]]; then
      local label="com.cityeye.camera${camera_id#camera-}"
      local plist="$LAUNCHD_DIR/$label.plist"
      if launchctl print "$LAUNCH_DOMAIN/$label" >/dev/null 2>&1; then
        echo "$camera_name already managed by launchd"
        continue
      fi
      launchctl bootstrap "$LAUNCH_DOMAIN" "$plist" 2>/dev/null || true
      launchctl kickstart "$LAUNCH_DOMAIN/$label"
      echo "Started $camera_name with launchd ($label)"
      continue
    fi

    if is_running "$pid_file"; then
      echo "$camera_name already running (PID $(cat "$pid_file"))"
      continue
    fi

    mkdir -p "$output_dir"
    nohup env CITYEYE_RTSP_URL="$stream_url" "$PYTHON" process_video.py \
      --config "$CONFIG" \
      --camera-id "$camera_id" \
      --camera-name "$camera_name" \
      --output-dir "$output_dir" \
      >"$output_dir/worker.log" 2>&1 &
    local launcher_pid="$!"
    echo "$launcher_pid" >"$pid_file"
    # Framework Python on macOS may hand execution to Python.app and exit the
    # launcher process. Resolve and persist the actual long-running worker.
    for _attempt in 1 2 3 4 5; do
      sleep 0.2
      local worker_pid
      worker_pid="$(find_worker_pid "$camera_id")"
      if [[ -n "$worker_pid" ]]; then
        echo "$worker_pid" >"$pid_file"
        break
      fi
    done
    echo "Started $camera_name (PID $(cat "$pid_file"))"
  done
}

stop_workers() {
  for camera_id in "${CAMERA_IDS[@]}"; do
    if [[ "$(uname -s)" == "Darwin" ]]; then
      local label="com.cityeye.camera${camera_id#camera-}"
      launchctl bootout "$LAUNCH_DOMAIN/$label" 2>/dev/null || true
      for _attempt in {1..30}; do
        if ! launchctl print "$LAUNCH_DOMAIN/$label" >/dev/null 2>&1; then
          break
        fi
        sleep 0.1
      done
      echo "Stopped $camera_id launchd service"
      continue
    fi
    local pid_file="$RUNTIME_DIR/$camera_id.pid"
    if ! is_running "$pid_file"; then
      local discovered_pid
      discovered_pid="$(find_worker_pid "$camera_id")"
      if [[ -n "$discovered_pid" ]]; then
        echo "$discovered_pid" >"$pid_file"
      fi
    fi
    if is_running "$pid_file"; then
      local pid
      pid="$(cat "$pid_file")"
      kill "$pid"
      echo "Stopped $camera_id (PID $pid)"
    fi
    rm -f "$pid_file"
  done
}

show_status() {
  for camera_id in "${CAMERA_IDS[@]}"; do
    if ! camera_is_enabled "$camera_id"; then
      echo "$camera_id worker: DISABLED"
      continue
    fi
    if [[ "$(uname -s)" == "Darwin" ]]; then
      local label="com.cityeye.camera${camera_id#camera-}"
      if launchctl print "$LAUNCH_DOMAIN/$label" >/dev/null 2>&1; then
        local launch_pid
        launch_pid="$(launchctl print "$LAUNCH_DOMAIN/$label" | awk '/pid =/{print $3; exit}')"
        echo "$camera_id worker: RUNNING (launchd PID ${launch_pid:-starting})"
      else
        echo "$camera_id worker: STOPPED"
      fi
      local status_file="$AI_DIR/live_output/$camera_id/camera_status.json"
      if [[ -f "$status_file" ]]; then
        "$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("  camera state:", d.get("state"), "capture:", round(d.get("camera_capture_fps",0),1), "preview:", round(d.get("preview_publication_fps",0),1), "AI:", round(d.get("ai_inference_fps",d.get("processing_fps",0)),1), "error:", d.get("last_error"))' "$status_file"
      else
        echo "  camera state: WAITING FOR FIRST STATUS"
      fi
      continue
    fi
    local pid_file="$RUNTIME_DIR/$camera_id.pid"
    if ! is_running "$pid_file"; then
      local discovered_pid
      discovered_pid="$(find_worker_pid "$camera_id")"
      if [[ -n "$discovered_pid" ]]; then
        echo "$discovered_pid" >"$pid_file"
      fi
    fi
    local status_file="$AI_DIR/live_output/$camera_id/camera_status.json"
    if is_running "$pid_file"; then
      echo "$camera_id worker: RUNNING (PID $(cat "$pid_file"))"
    else
      echo "$camera_id worker: STOPPED"
    fi
    if [[ -f "$status_file" ]]; then
      "$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("  camera state:", d.get("state"), "fps:", d.get("processing_fps", 0), "error:", d.get("last_error"))' "$status_file"
    else
      echo "  camera state: WAITING FOR FIRST STATUS"
    fi
  done
}

case "${1:-status}" in
  start) start_workers ;;
  stop) stop_workers ;;
  restart) stop_workers; start_workers ;;
  status) show_status ;;
  *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
