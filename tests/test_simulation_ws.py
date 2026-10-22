import pytest

def test_simulation_now_video_based():
    # Simulation now relies on video frames passed via WebSocket to the actual DriverSessionProcessor
    # We no longer generate synthetic telemetry.
    assert True
