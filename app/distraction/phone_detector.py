"""
Phone Object Detection Module.

Integrates a lightweight MobileNetV3-Large SSDLite model (pretrained on COCO)
for detecting mobile phones in driver monitoring camera footage.

Includes:
- COCO category 77 ('cell phone') filtering.
- Infrared / grayscale preprocessing adaptation (CLAHE contrast normalization).
- Real-time CPU-optimized inference with resolution scaling.
- Graceful fallback and dependency injection support for unit testing.

Note on Infrared Footage:
COCO weights are trained on visible-spectrum photography. Under active infrared
illumination (850nm/940nm), phone materials, display polarizers, and bezels
reflect light differently. Preprocessing (CLAHE) normalizes luminance and enhances
local gradients, but performance must be validated against real in-vehicle IR
recordings before deployment.
"""

import logging
from typing import Optional, Union, Tuple, List, Dict, Any
import cv2
import numpy as np
import torch
import torchvision.models.detection as detection_models

from app.distraction import config

logger = logging.getLogger(__name__)

# COCO label index for 'cell phone' in torchvision standard detection models
COCO_CELL_PHONE_LABEL = 77

# Common COCO categories recognized by torchvision SSDLite320 MobileNetV3
COCO_CLASSES: Dict[int, str] = {
    1: "person", 2: "bicycle", 3: "car", 4: "motorcycle", 5: "airplane", 6: "bus",
    7: "train", 8: "truck", 9: "boat", 10: "traffic light", 11: "fire hydrant",
    13: "stop sign", 14: "parking meter", 15: "bench", 16: "bird", 17: "cat",
    18: "dog", 19: "horse", 20: "sheep", 21: "cow", 22: "elephant", 23: "bear",
    24: "zebra", 25: "giraffe", 27: "backpack", 28: "umbrella", 31: "handbag",
    32: "tie", 33: "suitcase", 34: "frisbee", 35: "skis", 36: "snowboard",
    37: "sports ball", 38: "kite", 39: "baseball bat", 40: "baseball glove",
    41: "skateboard", 42: "surfboard", 43: "tennis racket", 44: "bottle",
    46: "wine glass", 47: "cup", 48: "fork", 49: "knife", 50: "spoon",
    51: "bowl", 52: "banana", 53: "apple", 54: "sandwich", 55: "orange",
    56: "broccoli", 57: "carrot", 58: "hot dog", 59: "pizza", 60: "donut",
    61: "cake", 62: "chair", 63: "couch", 64: "potted plant", 65: "bed",
    67: "dining table", 70: "toilet", 72: "tv", 73: "laptop", 74: "mouse",
    75: "remote", 76: "keyboard", 77: "cell phone", 78: "microwave", 79: "oven",
    80: "toaster", 81: "sink", 82: "refrigerator", 84: "book", 85: "clock",
    86: "vase", 87: "scissors", 88: "teddy bear", 89: "hair drier", 90: "toothbrush"
}


class PhoneDetector:
    """Detects mobile phones in camera frames using SSDLite320-MobileNetV3."""

    def __init__(
        self,
        confidence_threshold: float = config.DISTRACTION_CONFIDENCE_THRESHOLD,
        device: Optional[str] = None,
        model: Optional[Any] = None,
        lazy_load: bool = False,
    ):
        self.confidence_threshold = confidence_threshold
        self.device = torch.device(device if device else ("cuda" if torch.cuda.is_available() else "cpu"))
        self._model = model
        self._loaded = model is not None

        if not lazy_load and self._model is None:
            self._load_model()

    def _load_model(self) -> None:
        """Load pretrained SSDLite320 MobileNetV3 model."""
        if self._loaded and self._model is not None:
            return

        try:
            logger.info("Initializing SSDLite320 MobileNetV3 phone detector on %s...", self.device)
            weights = detection_models.SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
            model = detection_models.ssdlite320_mobilenet_v3_large(weights=weights)
            model.to(self.device)
            model.eval()
            self._model = model
            self._loaded = True
            logger.info("Phone detector model initialized successfully.")
        except Exception as e:
            logger.error("Failed to load phone detection model: %s", e)
            self._model = None
            self._loaded = False

    def preprocess_frame(self, frame: np.ndarray, is_infrared: bool = False) -> Tuple[torch.Tensor, Tuple[int, int]]:
        """
        Preprocess input camera frame for object detection.
        Accounts for single-channel grayscale or infrared footage.
        Returns:
            tensor (torch.Tensor): [1, 3, H, W] float tensor normalized to [0, 1]
            orig_shape (Tuple[int, int]): (original_h, original_w)
        """
        orig_h, orig_w = frame.shape[:2]

        # 1. Ensure 3-channel BGR/RGB representation
        if len(frame.shape) == 2 or frame.shape[2] == 1:
            frame_3ch = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            frame_3ch = frame.copy()

        # 2. Infrared preprocessing
        # IR footage is monochrome with distinct contrast issues under IR LEDs.
        # Apply CLAHE on the luminance channel to enhance phone edges and screen reflection boundaries.
        if is_infrared:
            lab = cv2.cvtColor(frame_3ch, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_enhanced = clahe.apply(l_channel)
            lab_enhanced = cv2.merge((l_enhanced, a_channel, b_channel))
            frame_3ch = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

        # 3. Resize to 320x320 for SSDLite mobile resolution
        input_resized = cv2.resize(frame_3ch, (320, 320), interpolation=cv2.INTER_AREA)

        # Convert to RGB (torchvision expectation) and normalize [0.0, 1.0]
        input_rgb = cv2.cvtColor(input_resized, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(input_rgb).permute(2, 0, 1).float().div(255.0).to(self.device)

        return tensor, (orig_h, orig_w)

    def detect(
        self,
        frame: np.ndarray,
        is_infrared: bool = False,
        confidence_threshold: Optional[float] = None,
        detect_all: bool = False,
        target_classes: Optional[Union[int, List[int]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detect mobile phones (and optionally other in-cabin objects) in the frame.

        Parameters:
            frame: Input image (BGR or grayscale).
            is_infrared: Whether frame is from an active IR illuminator / camera.
            confidence_threshold: Minimum confidence score filter.
            detect_all: If True, returns all recognized COCO classes.
            target_classes: Specific class IDs to filter for. Defaults to [COCO_CELL_PHONE_LABEL].

        Returns:
            List of detected objects with bounding boxes, confidence, class names, and centers.
        """
        if self._model is None:
            self._load_model()
            if self._model is None:
                return []

        conf_thresh = confidence_threshold if confidence_threshold is not None else self.confidence_threshold
        orig_h, orig_w = frame.shape[:2]

        if target_classes is None:
            targets = None if detect_all else [COCO_CELL_PHONE_LABEL]
        elif isinstance(target_classes, int):
            targets = [target_classes]
        else:
            targets = list(target_classes)

        try:
            tensor, _ = self.preprocess_frame(frame, is_infrared=is_infrared)

            with torch.no_grad():
                predictions = self._model([tensor])[0]

            boxes = predictions.get("boxes", [])
            scores = predictions.get("scores", [])
            labels = predictions.get("labels", [])

            detections: List[Dict[str, Any]] = []

            # Scale factors from 320x320 back to original frame dimensions
            scale_x = orig_w / 320.0
            scale_y = orig_h / 320.0

            for box, score, label in zip(boxes, scores, labels):
                score_val = float(score.item())
                label_val = int(label.item())

                # Confidence filtering
                if score_val < conf_thresh:
                    continue

                # Class filtering
                if targets is not None and label_val not in targets:
                    continue

                coords = box.cpu().numpy()
                x1 = max(0, int(coords[0] * scale_x))
                y1 = max(0, int(coords[1] * scale_y))
                x2 = min(orig_w, int(coords[2] * scale_x))
                y2 = min(orig_h, int(coords[3] * scale_y))

                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                class_name = COCO_CLASSES.get(label_val, f"object_{label_val}")

                detections.append({
                    "box": (x1, y1, x2, y2),
                    "confidence": round(score_val, 3),
                    "class_name": class_name,
                    "class_id": label_val,
                    "center": (cx, cy),
                })

            # Sort detections by confidence descending
            detections.sort(key=lambda d: d["confidence"], reverse=True)
            return detections

        except Exception as e:
            logger.warning("Error running phone detector: %s", e)
            return []

    def detect_objects(
        self,
        frame: np.ndarray,
        is_infrared: bool = False,
        confidence_threshold: Optional[float] = None,
        target_classes: Optional[Union[int, List[int]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detect recognized in-cabin and COCO objects for diagnostics and overlay.
        """
        detect_all = target_classes is None
        return self.detect(
            frame=frame,
            is_infrared=is_infrared,
            confidence_threshold=confidence_threshold,
            detect_all=detect_all,
            target_classes=target_classes,
        )


