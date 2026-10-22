from typing import Dict, Any

def get_scenario_telemetry(scenario_name: str, elapsed: float) -> Dict[str, Any]:
    """
    Returns simulated sensor and telemetry data based on the scenario name and elapsed time.
    Extensible for future hardware (IR, alcohol sensors, etc.).
    """
    # Default baseline inputs
    telemetry = {
        "ear": 0.35,
        "mar": 0.05,
        "pitch": 0.0,
        "face_detected": True,
        "cnn_p": 0.1,
        "cnn_failure": False,
        "camera_type": "webcam", # or 'ir'
        "alcohol_level": None,
        "alcohol_detected": False,
        "simulate_disconnect": False
    }

    if scenario_name == "NORMAL":
        pass
    elif scenario_name == "NORMAL BLINK":
        if 1.0 < elapsed < 1.15:
            telemetry["ear"] = 0.1
    elif scenario_name == "ACTIVE BLINKING":
        if int(elapsed * 4) % 2 == 0:
            telemetry["ear"] = 0.1
    elif scenario_name == "YAWNING":
        if 1.0 < elapsed < 4.0:
            telemetry["mar"] = 0.5
    elif scenario_name == "DROWSY":
        if int(elapsed * 2) % 2 == 0:
            telemetry["ear"] = 0.15
        telemetry["cnn_p"] = 0.6
    elif scenario_name == "SLEEPY":
        if elapsed > 1.0:
            telemetry["ear"] = 0.15
        telemetry["cnn_p"] = 0.75
    elif scenario_name == "LONG EYE CLOSURE":
        if elapsed > 1.0:
            telemetry["ear"] = 0.15
    elif scenario_name == "CRITICAL DROWSINESS":
        if elapsed > 1.0:
            telemetry["ear"] = 0.1
        telemetry["cnn_p"] = 0.85
    elif scenario_name == "HEAD NOD":
        if 1.0 < elapsed < 2.5:
            telemetry["pitch"] = -25.0
    elif scenario_name == "RECOVERY":
        telemetry["ear"] = 0.35
        telemetry["cnn_p"] = 0.1
    elif scenario_name == "FACE LOST":
        telemetry["face_detected"] = False
    elif scenario_name == "CAMERA DISCONNECTED":
        telemetry["simulate_disconnect"] = True
    elif scenario_name == "CNN INFERENCE FAILURE":
        telemetry["cnn_failure"] = True
    
    # Future scenarios can easily be added here
    elif scenario_name == "ALCOHOL DETECTED":
        telemetry["alcohol_detected"] = True
        telemetry["alcohol_level"] = 0.08
    elif scenario_name == "ALCOHOL + DROWSINESS":
        telemetry["alcohol_detected"] = True
        telemetry["alcohol_level"] = 0.08
        telemetry["cnn_p"] = 0.7
    elif scenario_name == "IR NIGHT MONITORING":
        telemetry["camera_type"] = "ir"
    elif scenario_name == "IR + DROWSINESS":
        telemetry["camera_type"] = "ir"
        if elapsed > 1.0:
            telemetry["ear"] = 0.15
        telemetry["cnn_p"] = 0.85

    return telemetry
