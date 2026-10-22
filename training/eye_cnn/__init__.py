"""
training.eye_cnn — Lightweight CNN for binary sleepiness classification.

Classes:
    0 = awake   (driver appears alert / eyes open)
    1 = sleepy  (driver appears drowsy / eyes closing)

The CNN is trained offline on the MRL Eye Dataset (forked, awake/sleepy split)
and is completely optional.  If model weights are absent the existing
EAR/MAR/PERCLOS pipeline continues to function without modification.
"""

CLASS_NAMES = ("awake", "sleepy")
CLASS_TO_IDX = {"awake": 0, "sleepy": 1}
IDX_TO_CLASS = {0: "awake", 1: "sleepy"}

INPUT_SIZE = 32       # pixels (height = width)
INPUT_CHANNELS = 1    # grayscale
NUM_CLASSES = 2
