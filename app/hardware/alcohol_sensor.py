"""
MQ-3 Alcohol Sensor Serial Reader & Prototype Lockout Manager.

Background daemon service that continuously reads serial telemetry from
the Arduino Nano connected to an MQ-3 alcohol sensor, manages warm-up and
clean-air baseline calibration, evaluates potential-alcohol detection with
persistence and hysteresis, and manages the backend-enforced vehicle lockout.

Arduino output format:
    "Analog: 70 | Digital: 1"

Requirements:
- Non-blocking thread-safe reader
- Configurable COM port, baud rate, threshold, and persistence
- Clean-air warm-up and calibration state handling
- Persistent vehicle safety lockout on POTENTIAL_ALCOHOL_DETECTED
- Separate alarm acknowledgement (does not clear lockout)
- Authenticated owner resolution with recorded audit reason
- Lockout persistence across restarts, reconnects, and reading drops
"""

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False

from app.config import settings
from app.database.connection import get_connection_context

logger = logging.getLogger(__name__)

# Sensor state machine constants
STATE_WARMING_UP = "WARMING_UP"
STATE_CALIBRATING = "CALIBRATING"
STATE_NORMAL = "NORMAL"
STATE_POTENTIAL_ALCOHOL = "POTENTIAL_ALCOHOL_DETECTED"
STATE_SENSOR_DISCONNECTED = "SENSOR_DISCONNECTED"
STATE_SENSOR_FAULT = "SENSOR_FAULT"

DISCLAIMER_TEXT = "MQ-3 is an alcohol-vapor prototype sensor, not a certified evidentiary breathalyzer."

# Regex strictly matching: "Analog: 70 | Digital: 1"
READING_REGEX = re.compile(
    r"^Analog:\s*(\d+)\s*\|\s*Digital:\s*([01])$",
    re.IGNORECASE,
)


class MQ3SerialReader:
    """
    Reusable, non-blocking serial reader and lockout manager for MQ-3 sensor hardware.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baud_rate: Optional[int] = None,
        warmup_duration_s: Optional[float] = None,
        calibration_samples: Optional[int] = None,
        threshold: Optional[int] = None,
        hysteresis: Optional[int] = None,
        persistence_count: Optional[int] = None,
        reconnect_interval_s: float = 2.0,
        read_timeout_s: float = 1.0,
    ):
        self.port: str = port or getattr(settings, "MQ3_SERIAL_PORT", "COM7")
        self.baud_rate: int = baud_rate or getattr(settings, "MQ3_BAUD_RATE", 9600)
        self.warmup_duration_s: float = warmup_duration_s if warmup_duration_s is not None else getattr(settings, "MQ3_WARMUP_SECONDS", 15.0)
        self.calibration_sample_target: int = calibration_samples if calibration_samples is not None else getattr(settings, "MQ3_CALIBRATION_SAMPLES", 10)
        self.threshold: int = threshold if threshold is not None else getattr(settings, "MQ3_ALCOHOL_THRESHOLD", 200)
        self.hysteresis: int = hysteresis if hysteresis is not None else getattr(settings, "MQ3_HYSTERESIS", 30)
        self.persistence_threshold: int = persistence_count if persistence_count is not None else getattr(settings, "MQ3_PERSISTENCE_COUNT", 3)
        self.reconnect_interval_s: float = reconnect_interval_s
        self.read_timeout_s: float = read_timeout_s

        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Telemetry & State machine
        self._is_connected: bool = False
        self._current_state: str = STATE_SENSOR_DISCONNECTED
        self._analog_value: Optional[int] = None
        self._digital_value: Optional[int] = None
        self._baseline: Optional[float] = None
        self._calibration_samples: List[int] = []
        self._warmup_start_epoch: float = 0.0
        self._last_reading_timestamp: Optional[str] = None
        self._last_reading_epoch: float = 0.0
        self._total_readings: int = 0
        self._error_message: Optional[str] = None

        # Fault & Persistence counters
        self._consecutive_over_threshold: int = 0
        self._consecutive_fault_count: int = 0

        # Safety Lockout
        self._active_lockout: Optional[Dict[str, Any]] = None

        # Factory hook for unit test mocking
        self._serial_factory: Callable[..., Any] = serial.Serial if SERIAL_AVAILABLE else None

        # Restore any existing lockout from persistent DB on startup
        self._restore_lockout_from_db()

    # -----------------------------------------------------------------------
    # Lifecycle Controls
    # -----------------------------------------------------------------------

    def start(self) -> None:
        """Start the background serial reader thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._warmup_start_epoch = time.time()
            self._calibration_samples.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="MQ3-SerialReaderThread",
            )
            self._thread.start()
            logger.info("MQ-3 Serial Reader started. Port: %s @ %d baud", self.port, self.baud_rate)

    def stop(self) -> None:
        """Stop the background serial reader thread cleanly."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        with self._lock:
            self._is_connected = False
            if self._current_state not in (STATE_POTENTIAL_ALCOHOL,):
                self._current_state = STATE_SENSOR_DISCONNECTED
        logger.info("MQ-3 Serial Reader stopped.")

    # -----------------------------------------------------------------------
    # Parsing Logic
    # -----------------------------------------------------------------------

    @staticmethod
    def parse_line(line: str) -> Optional[Tuple[int, int]]:
        """
        Parse raw line from Arduino.
        Returns (analog_value, digital_value) if valid, or None if malformed/comment.
        """
        if not line:
            return None

        clean_line = line.strip()
        if clean_line.startswith("#") or clean_line.startswith("//"):
            return None

        match = READING_REGEX.match(clean_line)
        if not match:
            return None

        try:
            analog_val = int(match.group(1))
            digital_val = int(match.group(2))
            if 0 <= analog_val <= 1023 and digital_val in (0, 1):
                return analog_val, digital_val
        except (ValueError, TypeError):
            pass

        return None

    # -----------------------------------------------------------------------
    # State Processing & Evaluation
    # -----------------------------------------------------------------------

    def process_reading(self, analog: int, digital: int) -> None:
        """
        Thread-safe state machine update for each valid reading.
        Handles WARMING_UP, CALIBRATING, NORMAL, POTENTIAL_ALCOHOL_DETECTED, and SENSOR_FAULT.
        """
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._analog_value = analog
            self._digital_value = digital
            self._last_reading_epoch = now
            self._last_reading_timestamp = now_iso
            self._total_readings += 1
            self._is_connected = True

            # 1. Fault check (stuck on ground or rails: 0 or >= 1023)
            if analog <= 2 or analog >= 1022:
                self._consecutive_fault_count += 1
                if self._consecutive_fault_count >= 8:
                    self._update_state(STATE_SENSOR_FAULT)
                    return
            else:
                self._consecutive_fault_count = 0

            # 2. Warm-up Phase: readings are ignored for alcohol threshold evaluation
            if self._warmup_start_epoch == 0.0:
                self._warmup_start_epoch = now

            warmup_elapsed = now - self._warmup_start_epoch
            if warmup_elapsed < self.warmup_duration_s:
                self._update_state(STATE_WARMING_UP)
                return

            # 3. Clean-Air Calibration Phase: collect baseline samples
            if len(self._calibration_samples) < self.calibration_sample_target:
                self._calibration_samples.append(analog)
                self._update_state(STATE_CALIBRATING)
                if len(self._calibration_samples) >= self.calibration_sample_target:
                    self._baseline = round(sum(self._calibration_samples) / len(self._calibration_samples), 1)
                    self._update_state(STATE_NORMAL)
                    logger.info("MQ-3 Calibration Complete. Baseline: %.1f, Threshold: %d", self._baseline, self.threshold)
                return

            # 4. Normal / Detection Phase
            if analog >= self.threshold:
                self._consecutive_over_threshold += 1
                if self._consecutive_over_threshold >= self.persistence_threshold:
                    if self._current_state != STATE_POTENTIAL_ALCOHOL:
                        self._trigger_potential_alcohol(analog)
            else:
                # Hysteresis: reading must drop below (threshold - hysteresis) to clear sensor alert state
                clear_threshold = max(0, self.threshold - self.hysteresis)
                if analog < clear_threshold:
                    self._consecutive_over_threshold = 0
                    if self._current_state == STATE_POTENTIAL_ALCOHOL:
                        # Sensor condition cleared, but lockout remains active until authorized owner resolution!
                        self._update_state(STATE_NORMAL)
                        logger.info("MQ-3 vapor level dropped below clear threshold (%d < %d). Lockout remains active.", analog, clear_threshold)
                    elif self._current_state != STATE_NORMAL and self._current_state not in (STATE_SENSOR_FAULT,):
                        self._update_state(STATE_NORMAL)

    def _update_state(self, new_state: str) -> None:
        """Update sensor state with transition logging."""
        if self._current_state != new_state:
            logger.info("MQ-3 State Change: %s -> %s (Analog: %s, Threshold: %d)",
                        self._current_state, new_state, self._analog_value, self.threshold)
            self._current_state = new_state

    # -----------------------------------------------------------------------
    # Lockout Management
    # -----------------------------------------------------------------------

    def _trigger_potential_alcohol(self, analog: int) -> None:
        """Trigger potential alcohol state and activate persistent lockout."""
        self._update_state(STATE_POTENTIAL_ALCOHOL)
        now_iso = datetime.now(timezone.utc).isoformat()

        # If a lockout is already active and unresolved, prevent duplicate incidents
        if self._active_lockout and self._active_lockout.get("is_locked", False):
            self._active_lockout["last_reading"] = analog
            return

        event_id = f"ALC-{int(time.time())}"
        self._active_lockout = {
            "event_id": event_id,
            "detected_at": now_iso,
            "state": STATE_POTENTIAL_ALCOHOL,
            "raw_reading": analog,
            "baseline": self._baseline,
            "threshold": self.threshold,
            "is_locked": True,
            "is_acknowledged": False,
            "acknowledged_at": None,
            "is_resolved": False,
            "resolved_at": None,
            "resolved_by_owner_id": None,
            "resolution_reason": None,
            "message": "POTENTIAL ALCOHOL DETECTED — VEHICLE OPERATION RESTRICTED",
        }

        # Persist lockout to database so it survives page reloads / restarts
        self._persist_lockout_to_db()

        # Record incident in database and pause active sessions (vehicle operation restricted)
        self._create_alcohol_incident(analog)

    def _create_alcohol_incident(self, analog: int) -> None:
        """Record an alcohol detection incident in monitoring_incidents and pause active sessions."""
        try:
            with get_connection_context() as conn:
                # 1. Look for active or paused session
                s_row = conn.execute(
                    "SELECT session_id, driver_id, vehicle_id, owner_id FROM monitoring_sessions WHERE status IN ('ACTIVE', 'PAUSED') ORDER BY session_id DESC LIMIT 1"
                ).fetchone()

                # 2. If no active session, link to most recent session to satisfy FOREIGN KEY constraint
                if not s_row:
                    s_row = conn.execute(
                        "SELECT session_id, driver_id, vehicle_id, owner_id FROM monitoring_sessions ORDER BY session_id DESC LIMIT 1"
                    ).fetchone()

                now_iso = datetime.now(timezone.utc).isoformat()

                if s_row:
                    session_id = s_row["session_id"]
                    driver_id = s_row["driver_id"]
                    vehicle_id = s_row["vehicle_id"]
                    owner_id = s_row["owner_id"]
                else:
                    # Fresh database with no sessions: find first driver and initialize a pre-trip record
                    d_row = conn.execute("SELECT driver_id, owner_id FROM drivers LIMIT 1").fetchone()
                    if not d_row:
                        logger.warning("No drivers in database to associate alcohol incident.")
                        return
                    driver_id = d_row["driver_id"]
                    owner_id = d_row["owner_id"]
                    vehicle_id = None
                    init_cur = conn.execute(
                        "INSERT INTO monitoring_sessions (driver_id, owner_id, start_time, status) VALUES (?, ?, ?, 'COMPLETED')",
                        (driver_id, owner_id, now_iso),
                    )
                    conn.commit()
                    session_id = init_cur.lastrowid

                # Retrieve driver name and vehicle registration for evidence overlay
                d_name_row = conn.execute("SELECT name FROM drivers WHERE driver_id = ?", (driver_id,)).fetchone()
                driver_name = d_name_row["name"] if d_name_row and d_name_row["name"] else f"Driver #{driver_id}"
                vehicle_reg = None
                if vehicle_id:
                    v_row = conn.execute("SELECT registration_number FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)).fetchone()
                    if v_row:
                        vehicle_reg = v_row["registration_number"]

                # Retrieve most recent camera frame from active live monitoring or fallback
                captured_frame = None
                try:
                    from app.api.monitoring_ws import get_live_session_frame, get_any_active_frame
                    captured_frame = get_live_session_frame(session_id)
                    if captured_frame is None:
                        captured_frame = get_any_active_frame()
                except Exception as frame_err:
                    logger.debug("Could not retrieve live session frame: %s", frame_err)

                if captured_frame is None:
                    try:
                        import cv2
                        cap = cv2.VideoCapture(0)
                        if cap.isOpened():
                            ret, frame = cap.read()
                            if ret and frame is not None and getattr(frame, "size", 0) > 0:
                                captured_frame = frame
                        cap.release()
                    except Exception:
                        pass

                # Generate styled warning screenshot and save raw camera frame if captured
                evidence_rel_path = None
                try:
                    from app.drowsiness.evidence import generate_alcohol_lockout_evidence
                    evidence_rel_path, _ = generate_alcohol_lockout_evidence(
                        frame_bgr=captured_frame,
                        driver_name=driver_name,
                        driver_id=driver_id,
                        vehicle_registration=vehicle_reg,
                        session_id=session_id,
                        analog_value=analog,
                        threshold_value=self.threshold,
                    )
                except Exception as ev_err:
                    logger.warning("Could not generate alcohol lockout evidence screenshot: %s", ev_err)

                cursor = conn.execute(
                    """
                    INSERT INTO monitoring_incidents
                      (session_id, driver_id, vehicle_id, owner_id, timestamp, event_type, alert_level,
                       kss_score, ear, mar, perclos, head_pitch_deg, evidence_path, distraction_type, duration_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, driver_id, vehicle_id, owner_id, now_iso, "alcohol_detected", 3,
                     9.0, None, None, None, None, evidence_rel_path, f"MQ-3 Analog: {analog} (Threshold: {self.threshold})", None),
                )

                # Restrict vehicle operation: automatically transition any ACTIVE sessions to PAUSED
                conn.execute(
                    """
                    UPDATE monitoring_sessions
                    SET status = 'PAUSED', pause_started_at = ?
                    WHERE status = 'ACTIVE' AND end_time IS NULL
                    """,
                    (now_iso,),
                )
                conn.commit()
                inc_id = cursor.lastrowid
                logger.warning("SAFETY LOCKOUT: Created alcohol incident #%s (Session: %s, Reading: %d) & restricted active sessions",
                               inc_id, session_id, analog)
                if self._active_lockout:
                    self._active_lockout["incident_id"] = inc_id

            # Update live session metrics cache immediately
            try:
                from app.api.monitoring_ws import LIVE_SESSION_METRICS, update_live_session_pause_state
                for sid in list(LIVE_SESSION_METRICS.keys()):
                    update_live_session_pause_state(sid, is_paused=True)
                    if sid in LIVE_SESSION_METRICS:
                        LIVE_SESSION_METRICS[sid]["is_locked"] = True
            except Exception:
                pass
        except Exception as e:
            logger.error("Failed to insert alcohol incident: %s", e)

    def is_locked(self) -> bool:
        """Check if vehicle is locked out due to potential alcohol detection."""
        with self._lock:
            return bool(self._active_lockout and self._active_lockout.get("is_locked", False))

    def get_active_lockout(self) -> Optional[Dict[str, Any]]:
        """Return active lockout details if locked."""
        with self._lock:
            if self._active_lockout and self._active_lockout.get("is_locked", False):
                return dict(self._active_lockout)
            return None

    def acknowledge_alarm(self) -> Dict[str, Any]:
        """
        Acknowledge and silence the audio alarm in prototype mode.
        Does NOT unlock the vehicle. Lockout remains active pending owner clearance.
        """
        with self._lock:
            if not self._active_lockout or not self._active_lockout.get("is_locked", False):
                return {"success": False, "message": "No active lockout to acknowledge."}

            now_iso = datetime.now(timezone.utc).isoformat()
            self._active_lockout["is_acknowledged"] = True
            self._active_lockout["acknowledged_at"] = now_iso
            self._persist_lockout_to_db()

            logger.info("Alcohol alarm acknowledged at %s (vehicle remains locked out).", now_iso)
            return {
                "success": True,
                "is_acknowledged": True,
                "is_locked": True,
                "message": "Alarm acknowledged. Vehicle lockout remains active pending owner clearance.",
                "lockout": dict(self._active_lockout),
            }

    def resolve_lockout(self, owner_id: int, reason: str) -> Dict[str, Any]:
        """
        Authorized owner clears the safety lockout with an audit reason.
        """
        with self._lock:
            if not self._active_lockout or not self._active_lockout.get("is_locked", False):
                return {"success": False, "message": "No active lockout to resolve."}

            now_iso = datetime.now(timezone.utc).isoformat()
            self._active_lockout["is_locked"] = False
            self._active_lockout["is_resolved"] = True
            self._active_lockout["resolved_at"] = now_iso
            self._active_lockout["resolved_by_owner_id"] = owner_id
            self._active_lockout["resolution_reason"] = reason

            self._clear_lockout_from_db()
            logger.info("Alcohol lockout resolved by Owner #%d at %s: '%s'", owner_id, now_iso, reason)

            resolved_event = dict(self._active_lockout)
            self._active_lockout = None

            # If current reading is below threshold, return to NORMAL
            if self._analog_value is not None and self._analog_value < self.threshold:
                self._update_state(STATE_NORMAL)

            try:
                from app.api.monitoring_ws import LIVE_SESSION_METRICS
                for sid, data in LIVE_SESSION_METRICS.items():
                    data["is_locked"] = False
            except Exception:
                pass

            return {
                "success": True,
                "message": "Safety lockout successfully resolved by authorized owner.",
                "resolved_event": resolved_event,
            }

    # -----------------------------------------------------------------------
    # Database Persistence
    # -----------------------------------------------------------------------

    def _persist_lockout_to_db(self) -> None:
        """Persist active lockout state into system_metadata."""
        if not self._active_lockout:
            return
        try:
            with get_connection_context() as conn:
                payload = json.dumps(self._active_lockout)
                conn.execute(
                    "INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('active_alcohol_lockout', ?)",
                    (payload,),
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to persist alcohol lockout to DB: %s", e)

    def _clear_lockout_from_db(self) -> None:
        """Remove active lockout from system_metadata upon owner resolution."""
        try:
            with get_connection_context() as conn:
                conn.execute("DELETE FROM system_metadata WHERE key = 'active_alcohol_lockout'")
                conn.commit()
        except Exception as e:
            logger.error("Failed to clear alcohol lockout from DB: %s", e)

    def _restore_lockout_from_db(self) -> None:
        """Restore active lockout on startup if one was unresolved."""
        try:
            with get_connection_context() as conn:
                row = conn.execute("SELECT value FROM system_metadata WHERE key = 'active_alcohol_lockout'").fetchone()
                if row:
                    val = row["value"] if hasattr(row, "__getitem__") else row[0]
                    self._active_lockout = json.loads(val)
                    if self._active_lockout and self._active_lockout.get("is_locked", False):
                        logger.warning("RESTORED ACTIVE ALCOHOL LOCKOUT FROM DATABASE: %s",
                                       self._active_lockout.get("event_id"))
                        now_iso = datetime.now(timezone.utc).isoformat()
                        conn.execute(
                            "UPDATE monitoring_sessions SET status = 'PAUSED', pause_started_at = ? WHERE status = 'ACTIVE' AND end_time IS NULL",
                            (now_iso,),
                        )
                        conn.commit()
        except Exception as e:
            logger.error("Failed to restore alcohol lockout from DB: %s", e)

    # -----------------------------------------------------------------------
    # Background Serial Loop
    # -----------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Continuously manages serial connection and processes incoming lines."""
        while self._running:
            if not self._serial_factory:
                with self._lock:
                    self._is_connected = False
                    self._current_state = STATE_SENSOR_DISCONNECTED
                    self._error_message = "Serial factory not configured"
                time.sleep(self.reconnect_interval_s)
                continue

            active_port = self._resolve_port()
            if not active_port:
                with self._lock:
                    self._is_connected = False
                    if self._current_state != STATE_POTENTIAL_ALCOHOL:
                        self._current_state = STATE_SENSOR_DISCONNECTED
                    self._error_message = f"Port '{self.port}' not available"
                time.sleep(self.reconnect_interval_s)
                continue

            ser = None
            try:
                ser = self._serial_factory(active_port, self.baud_rate, timeout=self.read_timeout_s)
                with self._lock:
                    self._is_connected = True
                    self._error_message = None
                    self.port = active_port
                    if self._warmup_start_epoch == 0.0:
                        self._warmup_start_epoch = time.time()
                logger.info("Connected to MQ-3 on %s @ %d baud", active_port, self.baud_rate)

                if hasattr(ser, "reset_input_buffer"):
                    ser.reset_input_buffer()

                while self._running:
                    raw_bytes = ser.readline()
                    if not raw_bytes:
                        continue

                    try:
                        decoded = raw_bytes.decode("utf-8", errors="replace").strip()
                    except Exception:
                        continue

                    parsed = self.parse_line(decoded)
                    if parsed is not None:
                        analog, digital = parsed
                        self.process_reading(analog, digital)

            except Exception as err:
                with self._lock:
                    self._is_connected = False
                    if self._current_state != STATE_POTENTIAL_ALCOHOL:
                        self._current_state = STATE_SENSOR_DISCONNECTED
                    self._error_message = str(err)
                logger.warning("Serial connection error on %s: %s (will retry)", active_port, err)
                time.sleep(self.reconnect_interval_s)
            finally:
                if ser:
                    try:
                        ser.close()
                    except Exception:
                        pass
                with self._lock:
                    self._is_connected = False

    def _resolve_port(self) -> Optional[str]:
        if not SERIAL_AVAILABLE:
            return None
        try:
            available = [p.device for p in serial.tools.list_ports.comports()]
            if self.port in available:
                return self.port
        except Exception:
            pass

        try:
            for p in serial.tools.list_ports.comports():
                desc = (p.description or "").lower()
                hwid = (p.hwid or "").lower()
                mfg = (p.manufacturer or "").lower()
                if "1a86:7523" in hwid or "ch340" in desc or "wch" in mfg or "usb-serial" in desc:
                    return p.device
        except Exception:
            pass
        return None

    # -----------------------------------------------------------------------
    # Public State Accessor
    # -----------------------------------------------------------------------

    def get_latest_reading(self) -> Dict[str, Any]:
        """Return thread-safe telemetry snapshot."""
        with self._lock:
            now = time.time()
            warmup_elapsed = max(0.0, now - self._warmup_start_epoch) if self._warmup_start_epoch > 0 else 0.0
            warmup_remaining = max(0.0, self.warmup_duration_s - warmup_elapsed) if self._current_state == STATE_WARMING_UP else 0.0

            is_locked = bool(self._active_lockout and self._active_lockout.get("is_locked", False))

            # Stale check: if no reading received within 3.0s or disconnected, clear live reading
            is_stale = (self._last_reading_epoch > 0 and (now - self._last_reading_epoch) > 3.0)
            is_alive = self._is_connected and not is_stale

            effective_state = self._current_state
            if not is_alive and not is_locked and effective_state not in (STATE_WARMING_UP, STATE_CALIBRATING, STATE_SENSOR_FAULT):
                effective_state = STATE_SENSOR_DISCONNECTED

            return {
                "status": "connected" if is_alive else "disconnected",
                "is_connected": is_alive,
                "state": effective_state,
                "port": self.port,
                "baud_rate": self.baud_rate,
                "analog": self._analog_value,
                "digital": self._digital_value,
                "baseline": self._baseline,
                "threshold": self.threshold,
                "hysteresis": self.hysteresis,
                "persistence_count": self.persistence_threshold,
                "warmup_remaining_seconds": round(warmup_remaining, 1),
                "timestamp": self._last_reading_timestamp,
                "total_readings": self._total_readings,
                "is_locked": is_locked,
                "lockout": dict(self._active_lockout) if self._active_lockout else None,
                "error": self._error_message,
                "disclaimer": DISCLAIMER_TEXT,
            }

    # -----------------------------------------------------------------------
    # Testing & Calibration Hooks
    # -----------------------------------------------------------------------

    def set_serial_factory(self, factory: Callable[..., Any]) -> None:
        self._serial_factory = factory

    def feed_line_for_testing(self, line: str) -> bool:
        """Inject a single line directly into parser for unit testing."""
        parsed = self.parse_line(line)
        if parsed is not None:
            analog, digital = parsed
            self.process_reading(analog, digital)
            return True
        return False

    def reset_state_for_testing(self) -> None:
        """Reset internal state machine for clean test isolation."""
        with self._lock:
            self._consecutive_over_threshold = 0
            self._consecutive_fault_count = 0
            self._calibration_samples.clear()
            self._baseline = None
            self._active_lockout = None
            self._warmup_start_epoch = time.time()
            self._current_state = STATE_NORMAL
        self._clear_lockout_from_db()


# Global singleton serial reader instance
mq3_serial_reader = MQ3SerialReader()
