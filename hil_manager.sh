#!/usr/bin/env bash
set -u

PID_FILE=".sim.pid"
SIM_LOG="reports/sim.log"
SCENARIO="normal"
DURATION=18

usage() {
    echo "Usage: $0 start [--scenario <normal|overheating|overheating_handled|rpm_spike>] [--duration <sec>]"
    echo "       $0 stop"
    echo "       $0 status"
    exit 1
}

teardown() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "[manager] Stopping sensor_sim.py (PID $pid)..."
            kill "$pid" 2>/dev/null
            wait "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi
}

if [[ $# -lt 1 ]]; then
    usage
fi

CMD="$1"
shift

case "$CMD" in
    stop)
        teardown
        exit 0
        ;;
    status)
        if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "[manager] Simulator running (PID $(cat "$PID_FILE"))"
        else
            echo "[manager] Simulator not running"
        fi
        exit 0
        ;;
    start)
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --scenario)
                    SCENARIO="${2:-normal}"
                    shift 2
                    ;;
                --duration)
                    DURATION="${2:-18}"
                    shift 2
                    ;;
                *)
                    echo "Unknown option: $1"
                    usage
                    ;;
            esac
        done
        ;;
    *)
        usage
        ;;
esac

mkdir -p reports

# Kill stale instance if still around
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    teardown
fi

trap teardown EXIT INT TERM

echo "[manager] Starting ECU simulator in background (scenario=$SCENARIO)..."
nohup python3 src/sensor_sim.py --error "$SCENARIO" > "$SIM_LOG" 2>&1 &
SIM_PID=$!
echo "$SIM_PID" > "$PID_FILE"

sleep 0.4
if ! kill -0 "$SIM_PID" 2>/dev/null; then
    echo "[manager] Error: sensor_sim.py failed to start. Check $SIM_LOG"
    exit 1
fi

echo "[manager] Running validation suite..."
python3 src/test_runner.py --duration "$DURATION"
EXIT_CODE=$?

echo "[manager] Run finished with exit code $EXIT_CODE"
exit $EXIT_CODE
