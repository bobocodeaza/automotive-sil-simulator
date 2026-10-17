#!/usr/bin/env python3
import argparse
import json
import random
import socket
import sys
import time

UDP_IP = "127.0.0.1"
UDP_PORT = 5000
TICK_RATE = 0.1  # 10 Hz


def get_args():
    parser = argparse.ArgumentParser(description="ECU UDP telemetry generator")
    parser.add_argument(
        "--error",
        type=str,
        default="normal",
        choices=["normal", "overheating", "overheating_handled", "rpm_spike"],
        help="Fault injection scenario",
    )
    parser.add_argument("--host", type=str, default=UDP_IP)
    parser.add_argument("--port", type=int, default=UDP_PORT)
    return parser.parse_args()


def build_frame(elapsed: float, fault: str, overheat_ts: float | None) -> dict:
    braking = random.random() < 0.15
    if braking:
        speed = round(random.uniform(40.0, 75.0), 1)
        rpm = random.randint(1500, 2800)
    else:
        speed = round(random.uniform(80.0, 130.0), 1)
        rpm = random.randint(2500, 5800)

    temp = round(random.uniform(88.0, 94.0), 2)
    safe_mode = False

    # Trigger radiator failure after 10s
    if fault in ("overheating", "overheating_handled") and elapsed >= 10.0:
        dt = elapsed - 10.0
        temp = round(min(145.0, 90.0 + (1.45 ** dt) * 2.5), 2)

        if temp > 110.0 and overheat_ts is not None:
            # 'overheating' simulates a lagging ECU (>2s safety requirement)
            delay = 0.8 if fault == "overheating_handled" else 3.2
            if (time.time() - overheat_ts) >= delay:
                safe_mode = True

    # Stuck throttle after 8s
    if fault == "rpm_spike" and elapsed >= 8.0:
        rpm = random.randint(6700, 7400)

    return {
        "timestamp": round(time.time(), 4),
        "elapsed_sec": round(elapsed, 2),
        "speed_kmh": speed,
        "rpm": rpm,
        "engine_temp_c": temp,
        "brake_active": braking,
        "ecu_safe_mode": safe_mode,
        "scenario": fault,
    }


def main():
    args = get_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    start_ts = time.time()
    overheat_ts = None

    print(f"[sim] Sending UDP frames to {args.host}:{args.port} (mode={args.error})", flush=True)

    try:
        while True:
            now = time.time()
            frame = build_frame(now - start_ts, args.error, overheat_ts)

            if frame["engine_temp_c"] > 110.0 and overheat_ts is None:
                overheat_ts = now

            sock.sendto(json.dumps(frame).encode("utf-8"), (args.host, args.port))
            time.sleep(TICK_RATE)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
