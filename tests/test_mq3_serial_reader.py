"""
Unit tests for MQ-3 Serial Reader.

Verifies:
- Line parsing of Arduino Nano format: "Analog: 70 | Digital: 1"
- Range validation (analog 0-1023, digital 0 or 1)
- Filtering and ignoring startup/comment lines and malformed data
- Non-blocking thread behavior and mock serial stream reading
- Error handling and disconnect recovery without exceptions crashing caller
- REST API endpoint GET /api/alcohol/status
"""

import time
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.hardware.alcohol_sensor import MQ3SerialReader, mq3_serial_reader


class MockSerialDevice:
    """Mock serial connection producing predefined lines."""

    def __init__(self, lines=None, fail_on_open=False, fail_on_read=False):
        self.lines = list(lines or [])
        self.fail_on_open = fail_on_open
        self.fail_on_read = fail_on_read
        self.is_open = True
        self.closed = False
        if fail_on_open:
            import serial
            raise serial.SerialException("Mock port opening failed: device not found")

    def readline(self) -> bytes:
        if self.fail_on_read:
            import serial
            raise serial.SerialException("Mock device disconnected during read")
        if self.lines:
            line = self.lines.pop(0)
            return (line + "\r\n").encode("utf-8")
        time.sleep(0.05)
        return b""

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False
        self.closed = True


# ---------------------------------------------------------------------------
# 1. Parsing Unit Tests
# ---------------------------------------------------------------------------

def test_parse_valid_readings():
    reader = MQ3SerialReader()

    assert reader.parse_line("Analog: 70 | Digital: 1") == (70, 1)
    assert reader.parse_line("Analog: 0 | Digital: 0") == (0, 0)
    assert reader.parse_line("Analog: 1023 | Digital: 1") == (1023, 1)
    assert reader.parse_line("analog: 250 | digital: 0") == (250, 0)
    assert reader.parse_line("  Analog:   68   |   Digital: 1  ") == (68, 1)


def test_ignore_startup_and_comments():
    reader = MQ3SerialReader()

    assert reader.parse_line("# MQ-3 Alcohol Sensor Initialized.") is None
    assert reader.parse_line("# Notice: Sensor heater stabilizing...") is None
    assert reader.parse_line("// debug text") is None
    assert reader.parse_line("") is None
    assert reader.parse_line("   ") is None


def test_ignore_malformed_readings():
    reader = MQ3SerialReader()

    # Out of bounds
    assert reader.parse_line("Analog: 1024 | Digital: 1") is None
    assert reader.parse_line("Analog: -1 | Digital: 1") is None
    assert reader.parse_line("Analog: 70 | Digital: 2") is None

    # Corrupted / partial strings
    assert reader.parse_line("Analog: abc | Digital: 1") is None
    assert reader.parse_line("Analog: 70") is None
    assert reader.parse_line("Digital: 1") is None
    assert reader.parse_line("Random garbage line from bootloader") is None


# ---------------------------------------------------------------------------
# 2. Mock Serial Stream & Non-Blocking Lifecycle Tests
# ---------------------------------------------------------------------------

def test_mock_serial_stream_reading():
    test_lines = [
        "# MQ-3 Alcohol Sensor Initialized.",
        "# Notice: Sensor heater stabilizing...",
        "Analog: 68 | Digital: 1",
        "corrupted line",
        "Analog: 72 | Digital: 1",
    ]

    reader = MQ3SerialReader(
        port="COM_TEST",
        baud_rate=9600,
        reconnect_interval_s=0.1,
        read_timeout_s=0.1,
    )
    # Inject mock serial device
    mock_dev = MockSerialDevice(lines=test_lines)
    reader.set_serial_factory(lambda *args, **kwargs: mock_dev)

    # Directly bypass port auto-discovery for test
    reader._resolve_port = lambda: "COM_TEST"

    reader.start()

    # Allow background thread to read through mock lines
    for _ in range(20):
        data = reader.get_latest_reading()
        if data["total_readings"] >= 2:
            break
        time.sleep(0.05)

    reader.stop()

    latest = reader.get_latest_reading()
    assert latest["total_readings"] == 2
    assert latest["analog"] == 72
    assert latest["digital"] == 1
    assert latest["timestamp"] is not None
    assert latest["is_connected"] is False  # Once stopped, is_connected is reset


def test_disconnect_and_reconnection_resilience():
    """Verify that serial failures do not raise unhandled exceptions and allow retry."""
    reader = MQ3SerialReader(
        port="COM_DISCONNECT_TEST",
        reconnect_interval_s=0.05,
        read_timeout_s=0.05,
    )
    reader._resolve_port = lambda: "COM_DISCONNECT_TEST"

    attempts = {"count": 0}

    def failing_factory(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            # First attempt: throws disconnect error
            return MockSerialDevice(fail_on_read=True)
        else:
            # Subsequent attempt: recovers with valid line
            return MockSerialDevice(lines=["Analog: 75 | Digital: 1"])

    reader.set_serial_factory(failing_factory)
    reader.start()

    for _ in range(25):
        data = reader.get_latest_reading()
        if data["total_readings"] >= 1:
            break
        time.sleep(0.05)

    reader.stop()

    latest = reader.get_latest_reading()
    assert latest["total_readings"] >= 1
    assert latest["analog"] == 75
    assert latest["digital"] == 1


# ---------------------------------------------------------------------------
# 3. REST API Status Endpoint Test
# ---------------------------------------------------------------------------

def test_api_alcohol_status_endpoint():
    # Inject a test line into the singleton reader
    mq3_serial_reader.feed_line_for_testing("Analog: 77 | Digital: 1")

    client = TestClient(app)
    response = client.get("/api/alcohol/status")

    assert response.status_code == 200
    json_data = response.json()

    assert json_data["is_connected"] is True
    assert json_data["analog"] == 77
    assert json_data["digital"] == 1
    assert json_data["timestamp"] is not None
    assert "port" in json_data
    assert "baud_rate" in json_data
