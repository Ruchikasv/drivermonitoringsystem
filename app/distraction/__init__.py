"""
Driver Distraction Detection Package.

Exports:
- PhoneDetector: Pre-trained mobile object detection for phones
- PhoneDistractionDetector: Temporal distraction tracking and alert logic
- config: Distraction thresholds and settings
"""

from app.distraction import config
from app.distraction.phone_detector import PhoneDetector
from app.distraction.distraction_detector import PhoneDistractionDetector

__all__ = ["PhoneDetector", "PhoneDistractionDetector", "config"]
