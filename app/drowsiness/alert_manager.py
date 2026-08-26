"""
Tiered alert escalation, mirroring how real automotive HMI/DMS systems
respond -- not a single "beep when eyes closed" alarm.

Tier 1 (NUDGE)    : mild PERCLOS rise / early yawn pattern -> gentle on-screen
                    nudge + soft tone
Tier 2 (WARNING)  : KSS 6-7 range -> clear audio + visual alert, suggests a
                    rest stop
Tier 3 (CRITICAL) : KSS >= 7 (Euro NCAP's own drowsy threshold) or a
                    microsleep event -> loud alert + simulated hazard/SOS:
                    GPS-tagged email to an emergency contact and a logged
                    incident record

Hardware note: no seat/steering haptics here since this is laptop-only --
the tiering and escalation logic is real, the actuator layer is simulated
(logged + optional real email). Swapping in real haptic/vehicle actuators
later only touches `_trigger_critical()`.
"""

import os
import smtplib
import time
import json
from email.mime.text import MIMEText

from app.drowsiness import config


class AlertManager:
    def __init__(self, log_path: str = None):
        self.log_path = log_path or config.INCIDENTS_LOG_PATH
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._last_alert_time = {"nudge": 0.0, "warning": 0.0, "critical": 0.0}
        self._in_critical_state = False
        self._normal_since = time.time()

    def _cooldown_ok(self, tier: str, now: float) -> bool:
        return (now - self._last_alert_time[tier]) >= config.ALERT_COOLDOWN_SECONDS

    def evaluate(self, fusion_result: dict) -> dict | None:
        """
        Evidence-grounded alert evaluation.
        Evaluates real-time multimodal telemetry and determines if an alert tier should fire.

        Alert Tiers:
        - None      : Awake, normal blinking (<1.5s), normal head pose, low PERCLOS.
        - 'nudge'   (Level 1): Mild sustained closure (1.5-1.8s), sustained yawn (>=1.5s), or mature PERCLOS >=18% with KSS >=5.0.
        - 'warning' (Level 2): Sustained closure (1.8-2.5s), sustained head nod (>=1.5s), repeated yawns, or PERCLOS >=30% with KSS >=6.5.
        - 'critical'(Level 3): Genuinely severe/prolonged closure (>=2.5s), multi-signal convergence (closure >=1.5s + head nod/yawn), or repeated microsleeps + high PERCLOS + KSS >=7.5.
        """
        now = fusion_result.get("timestamp", time.time())
        face_detected = fusion_result.get("face_detected", True)

        # If no face is detected, reset state and do not trigger alerts
        if not face_detected:
            self._in_critical_state = False
            return None

        kss = fusion_result.get("kss_now", 1.0)
        raw = fusion_result.get("raw_signals", {})
        perclos = raw.get("avg_perclos", 0.0)
        ear = fusion_result.get("ear", 0.30)
        mar = fusion_result.get("mar", 0.25)
        pitch = fusion_result.get("pitch", 0.0)

        sustained_eye_closure = fusion_result.get("sustained_eye_closure_seconds", 0.0)
        sustained_yawn = fusion_result.get("sustained_yawn_seconds", 0.0)
        sustained_nod = fusion_result.get("sustained_nod_seconds", 0.0)

        microsleeps_in_window = raw.get("microsleeps_in_window", 0)
        yawns_in_window = raw.get("yawns_in_window", 0)
        head_nods_in_window = raw.get("head_nods_in_window", 0)

        tier = None
        message = None
        reason = None

        # ------------------------------------------------------------------
        # 1. Check LEVEL 3 — CRITICAL HAZARD
        # ------------------------------------------------------------------
        if sustained_eye_closure >= 2.5 and ear < config.EAR_THRESHOLD:
            tier = "critical"
            reason = f"Prolonged eye closure / microsleep sustained for {sustained_eye_closure:.1f}s (EAR: {ear:.3f} < {config.EAR_THRESHOLD})"
            message = "CRITICAL: Prolonged eye closure detected. Pull over immediately."

        elif sustained_eye_closure >= 1.5 and ear < config.EAR_THRESHOLD and (pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG or sustained_yawn >= 1.5):
            tier = "critical"
            trigger_detail = f"head nod ({pitch:.1f}°)" if pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG else f"active yawn (MAR: {mar:.2f})"
            reason = f"Multi-signal fatigue: Sustained eye closure ({sustained_eye_closure:.1f}s) combined with {trigger_detail}"
            message = "CRITICAL: Multi-modal drowsiness detected. Pull over safely."

        elif microsleeps_in_window >= 2 and perclos >= 0.35 and kss >= 7.5:
            tier = "critical"
            reason = f"Repeated microsleeps ({microsleeps_in_window} in 60s) with severe PERCLOS ({(perclos*100):.1f}%) and high KSS ({kss:.1f}/9.0)"
            message = "CRITICAL: Severe fatigue pattern detected. Pull over safely."

        # ------------------------------------------------------------------
        # 2. Check LEVEL 2 — WARNING
        # ------------------------------------------------------------------
        elif sustained_eye_closure >= 1.8 and ear < config.EAR_THRESHOLD:
            tier = "warning"
            reason = f"Sustained eye closure for {sustained_eye_closure:.1f}s (EAR: {ear:.3f})"
            message = "WARNING: Signs of fatigue rising. Consider a rest stop soon."

        elif sustained_nod >= 1.5 and pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG:
            tier = "warning"
            reason = f"Downward head nod sustained for {sustained_nod:.1f}s (Pitch: {pitch:.1f}°)"
            message = "WARNING: Head dropping detected. Stay focused on the road."

        elif yawns_in_window >= 2 and kss >= 6.0:
            tier = "warning"
            reason = f"Frequent yawning ({yawns_in_window} in 60s) with elevated fatigue (KSS: {kss:.1f})"
            message = "WARNING: Multiple yawns detected. Plan a break soon."

        elif perclos >= 0.30 and kss >= 6.5:
            tier = "warning"
            reason = f"High cumulative eye closure (PERCLOS: {(perclos*100):.1f}%) with KSS: {kss:.1f}"
            message = "WARNING: Elevated drowsiness indicators. Stay alert."

        # ------------------------------------------------------------------
        # 3. Check LEVEL 1 — CAUTION / NUDGE
        # ------------------------------------------------------------------
        elif sustained_eye_closure >= 1.5 and ear < config.EAR_THRESHOLD:
            tier = "nudge"
            reason = f"Abnormal eye closure duration ({sustained_eye_closure:.1f}s)"
            message = "Notice: Slight increase in eye-closure detected. Stay alert."

        elif sustained_yawn >= 1.5 and mar > config.MAR_THRESHOLD:
            tier = "nudge"
            reason = f"Sustained yawn detected for {sustained_yawn:.1f}s (MAR: {mar:.2f})"
            message = "Notice: Yawning detected. Ensure adequate ventilation."

        elif perclos >= config.PERCLOS_WARN_THRESHOLD and kss >= 5.0:
            tier = "nudge"
            reason = f"Elevated eye closure time (PERCLOS: {(perclos*100):.1f}%)"
            message = "Notice: Fatigue indicators rising. Stay alert."

        # ------------------------------------------------------------------
        # 4. State Reset & Recovery
        # ------------------------------------------------------------------
        if tier is None:
            # Driver is alert and awake
            if ear >= config.EAR_THRESHOLD and sustained_eye_closure == 0.0:
                if now - self._normal_since >= 1.5:
                    self._in_critical_state = False
            return None

        self._normal_since = now

        # Prevent duplicate screenshot spam during an ongoing critical incident
        if tier == "critical":
            if self._in_critical_state:
                # Critical condition is still ongoing; don't spawn duplicate incidents every frame
                return None
            if not self._cooldown_ok("critical", now):
                return None
            self._in_critical_state = True
        else:
            if not self._cooldown_ok(tier, now):
                return None

        self._last_alert_time[tier] = now
        alert = {
            "timestamp": now,
            "tier": tier,
            "message": message,
            "reason": reason,
            "kss_now": kss,
            "p_critical_soon": fusion_result.get("p_critical_soon"),
        }

        self._log_incident(alert)
        if tier == "critical":
            self._trigger_critical(alert)

        return alert

    def _log_incident(self, alert: dict):
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(alert) + "\n")
        except Exception:
            pass

    def _trigger_critical(self, alert: dict):
        alert["gps"] = {"lat": config.SIMULATED_GPS_LAT, "lon": config.SIMULATED_GPS_LON}
        if config.ENABLE_EMAIL_SOS:
            try:
                self._send_sos_email(alert)
                alert["sos_email_sent"] = True
            except Exception as e:
                alert["sos_email_sent"] = False
                alert["sos_email_error"] = str(e)
        else:
            alert["sos_email_sent"] = False  # simulation mode, disabled by default

    def _send_sos_email(self, alert: dict):
        body = (
            f"Driver drowsiness CRITICAL alert.\n"
            f"Time: {time.ctime(alert['timestamp'])}\n"
            f"Reason: {alert.get('reason', 'Severe drowsiness')}\n"
            f"KSS score: {alert['kss_now']}\n"
            f"Simulated GPS: {alert['gps']['lat']}, {alert['gps']['lon']}\n"
            f"https://maps.google.com/?q={alert['gps']['lat']},{alert['gps']['lon']}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = "SOS: Driver Drowsiness Critical Alert"
        msg["From"] = config.EMAIL_SENDER
        msg["To"] = config.EMAIL_RECEIVER

        with smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_SENDER, config.EMAIL_APP_PASSWORD)
            server.sendmail(config.EMAIL_SENDER, [config.EMAIL_RECEIVER], msg.as_string())

