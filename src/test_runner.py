#!/usr/bin/env python3
import argparse
from collections import deque
from datetime import datetime
import json
import os
import socket
import sqlite3
import sys
import time


class TestCase:
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.details = "Nominal"
        self.done = False

    def evaluate(self, frame: dict, window: deque) -> None:
        raise NotImplementedError

    def format_result(self) -> str:
        tag = "PASS" if self.passed else "FAIL"
        return f"[{tag}] {self.name} - {self.details}"


class RPMTest(TestCase):
    MAX_RPM = 6500

    def __init__(self):
        super().__init__("Test RPM")
        self.max_seen = 0

    def evaluate(self, frame: dict, window: deque) -> None:
        rpm = frame.get("rpm", 0)
        if rpm > self.max_seen:
            self.max_seen = rpm

        if rpm > self.MAX_RPM and self.passed:
            self.passed = False
            self.details = f"Exceeded {self.MAX_RPM} RPM limit (got {rpm} RPM at t={frame.get('elapsed_sec')}s)"
            self.done = True
        elif self.passed:
            self.details = f"Within limits (peak: {self.max_seen} RPM)"


class OverheatingTest(TestCase):
    LIMIT_C = 110.0
    MAX_REACTION_SEC = 2.0

    def __init__(self):
        super().__init__("Test Overheating")
        self.threshold_ts = None
        self.peak_temp = 0.0

    def evaluate(self, frame: dict, window: deque) -> None:
        temp = frame.get("engine_temp_c", 0.0)
        ts = frame.get("timestamp", time.time())
        safe_mode = frame.get("ecu_safe_mode", False)

        if temp > self.peak_temp:
            self.peak_temp = temp

        # Temperature delta across the 50-sample sliding window
        delta = 0.0
        if len(window) >= 2:
            delta = round(window[-1]["engine_temp_c"] - window[0]["engine_temp_c"], 2)

        if temp > self.LIMIT_C:
            if self.threshold_ts is None:
                self.threshold_ts = ts
                print(f"[warn] Temp crossed {self.LIMIT_C}C ({temp}C, window delta: +{delta}C). Waiting for ECU safe mode...")

            dt = ts - self.threshold_ts

            if safe_mode and not self.done:
                if dt <= self.MAX_REACTION_SEC:
                    self.passed = True
                    self.details = f"Safe mode triggered in {dt:.2f}s (peak: {self.peak_temp}C)"
                else:
                    self.passed = False
                    self.details = f"Reaction time exceeded ({dt:.2f}s > {self.MAX_REACTION_SEC}s)"
                self.done = True

            elif dt > self.MAX_REACTION_SEC and self.passed:
                self.passed = False
                self.details = f"Reaction time exceeded ({dt:.2f}s > {self.MAX_REACTION_SEC}s, no safe mode at {temp}C)"
                self.done = True
        else:
            if self.threshold_ts is None and self.passed:
                self.details = f"Thermal regime nominal (peak: {self.peak_temp}C, window delta: {delta}C)"


def write_results(tests: list[TestCase], scenario: str, count: int, elapsed: float):
    os.makedirs("reports", exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join("reports", "test_report.log")
    db_file = os.path.join("reports", "hil_results.db")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"--- Run: {now_str} | Scenario: {scenario} | Packets: {count} | Duration: {elapsed:.1f}s ---\n")
        for t in tests:
            f.write(t.format_result() + "\n")
        f.write("\n")

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            scenario TEXT,
            test_name TEXT,
            status TEXT,
            details TEXT,
            samples INTEGER
        )
        """
    )
    for t in tests:
        cur.execute(
            "INSERT INTO test_runs (timestamp, scenario, test_name, status, details, samples) VALUES (?, ?, ?, ?, ?, ?)",
            (now_str, scenario, t.name, "PASS" if t.passed else "FAIL", t.details, count),
        )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="UDP HIL test runner")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--duration", type=float, default=18.0)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", args.port))
    sock.settimeout(3.0)

    # Keep last 50 readings (5s of data at 10Hz) for trend checks
    window = deque(maxlen=50)
    tests = [RPMTest(), OverheatingTest()]

    start_ts = time.time()
    packets = 0
    scenario = "unknown"

    print(f"[runner] Listening on UDP 127.0.0.1:{args.port} for {args.duration}s...")

    try:
        while (time.time() - start_ts) < args.duration:
            try:
                raw, _ = sock.recvfrom(4096)
            except socket.timeout:
                print("[runner] Socket timeout - no telemetry received.")
                break

            frame = json.loads(raw.decode("utf-8"))
            packets += 1
            scenario = frame.get("scenario", "unknown")
            window.append(frame)

            if packets % 10 == 0:
                print(
                    f"  t={frame['elapsed_sec']:>4.1f}s | "
                    f"spd={frame['speed_kmh']:>5.1f} km/h | "
                    f"rpm={frame['rpm']:>4d} | "
                    f"temp={frame['engine_temp_c']:>6.2f}C | "
                    f"brk={str(frame['brake_active']):<5} | "
                    f"safe={frame['ecu_safe_mode']}"
                )

            for t in tests:
                t.evaluate(frame, window)

            if any(t.done and not t.passed for t in tests):
                print("[runner] Critical failure caught, stopping test run early.")
                break

    except KeyboardInterrupt:
        print("\n[runner] Interrupted.")
    finally:
        sock.close()

    total_time = time.time() - start_ts
    write_results(tests, scenario, packets, total_time)

    print("\nTest Summary:")
    for t in tests:
        print("  " + t.format_result())
    print("Saved results to reports/test_report.log and reports/hil_results.db")

    sys.exit(0 if all(t.passed for t in tests) else 1)


if __name__ == "__main__":
    main()
