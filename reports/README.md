# Automotive SIL Telemetry & Test Runner

![SIL Validation CI](https://github.com/bobocodeaza/automotive-sil-simulator/actions/workflows/ci.yml/badge.svg)

Lightweight Software-in-the-Loop (SIL) testing setup for Linux/WSL. It simulates an ECU broadcasting telemetry over UDP and validates system behavior under injected faults.

## Components

- **`src/sensor_sim.py`** – Generates JSON telemetry packets at 10 Hz (`speed_kmh`, `rpm`, `engine_temp_c`, `brake_active`, `ecu_safe_mode`) and streams them over UDP (`127.0.0.1:5000`). Supports CLI fault injection (`--error`).
- **`src/test_runner.py`** – Listens on port 5000, buffers a 50-sample sliding window, and evaluates incoming frames against test cases:
  - `RPMTest`: Fails if engine speed exceeds 6500 RPM.
  - `OverheatingTest`: Checks if the ECU triggers `ecu_safe_mode` within 2.0 seconds after coolant temperature crosses 110°C.
- **`hil_manager.sh`** – Bash wrapper that starts the simulator in the background (`nohup`), tracks its PID, runs the test suite in the foreground, and handles process teardown on exit.

## Usage

Make the scripts executable:
```bash
chmod +x hil_manager.sh src/sensor_sim.py src/test_runner.py
