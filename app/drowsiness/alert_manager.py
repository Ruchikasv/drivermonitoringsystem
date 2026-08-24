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

    def _cooldown_ok(self, tier: str, now: float) -> bool:
        return (now - self._last_alert_time[tier]) >= config.ALERT_COOLDOWN_SECONDS

    def evaluate(self, fusion_result: dict) -> dict | None:
        """Given the latest fusion output, decide whether to fire an alert
        and at which tier. Returns the alert dict (also logged) or None."""
        now = fusion_result["timestamp"]
        kss = fusion_result["kss_now"]
        raw = fusion_result["raw_signals"]

        tier = None
        message = None

        if kss >= config.KSS_CRITICAL_THRESHOLD or raw["microsleeps_in_window"] > 0:
            tier = "critical"
            message = "CRITICAL: Driver drowsiness detected. Pull over safely."
        elif kss >= 6.0 or raw["yawn_rate_per_min"] >= 2:
            tier = "warning"
            message = "WARNING: Signs of fatigue rising. Consider a rest stop soon."
        elif raw["avg_perclos"] >= config.PERCLOS_WARN_THRESHOLD:
            tier = "nudge"
            message = "Notice: Slight increase in eye-closure detected. Stay alert."

        if tier is None or not self._cooldown_ok(tier, now):
            return None

        self._last_alert_time[tier] = now
        alert = {
            "timestamp": now,
            "tier": tier,
            "message": message,
            "kss_now": kss,
            "p_critical_soon": fusion_result.get("p_critical_soon"),
        }

        self._log_incident(alert)
        if tier == "critical":
            self._trigger_critical(alert)

        return alert

    def _log_incident(self, alert: dict):
        with open(self.log_path, "a") as f:
            f.write(json.dumps(alert) + "\n")

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
