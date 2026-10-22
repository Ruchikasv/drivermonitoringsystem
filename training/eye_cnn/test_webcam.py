import argparse
import collections
import os
import sys
import time

import cv2
import numpy as np
import onnxruntime as ort

from app.drowsiness.face_mesh import FaceMeshDetector, LEFT_EYE, RIGHT_EYE
from training.eye_cnn import IDX_TO_CLASS
from training.eye_cnn.preprocessing import preprocess_eye_image


def crop_eye(frame: np.ndarray, pts_px: np.ndarray, eye_indices: list, padding: float = 0.4):
    """Calculate bounding box for eye landmarks, apply padding, and crop."""
    eye_pts = pts_px[eye_indices]
    x_min = np.min(eye_pts[:, 0])
    x_max = np.max(eye_pts[:, 0])
    y_min = np.min(eye_pts[:, 1])
    y_max = np.max(eye_pts[:, 1])
    
    w = x_max - x_min
    h = y_max - y_min
    
    cx = x_min + w / 2
    cy = y_min + h / 2
    
    # Make it square with padding
    side = max(w, h) * (1 + padding)
    
    x1 = int(cx - side / 2)
    y1 = int(cy - side / 2)
    x2 = int(cx + side / 2)
    y2 = int(cy + side / 2)
    
    # Clip to frame boundaries
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(frame.shape[1], x2)
    y2 = min(frame.shape[0], y2)
    
    crop = frame[y1:y2, x1:x2]
    rect = (x1, y1, x2, y2)
    return crop, rect


def infer_with_session(sess, image: np.ndarray) -> dict:
    """Run inference using an existing ONNX Runtime session."""
    tensor = preprocess_eye_image(image)
    tensor_np = tensor.numpy()
    logits = sess.run(None, {"eye_image": tensor_np})[0]
    
    # Softmax
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = (exp / exp.sum(axis=1, keepdims=True)).squeeze()
    
    pred_idx = int(probs.argmax())
    
    # For visualization, convert the [-1, 1] preprocessed tensor back to [0, 255]
    vis_img = (tensor[0, 0].numpy() * 0.5 + 0.5) * 255.0
    vis_img = np.clip(vis_img, 0, 255).astype(np.uint8)
    
    return {
        "label": IDX_TO_CLASS[pred_idx].upper(),
        "confidence": float(probs[pred_idx]),
        "p_awake": float(probs[0]),
        "p_sleepy": float(probs[1]),
        "preprocessed": vis_img
    }


def main():
    parser = argparse.ArgumentParser(description="Standalone Eye CNN Inference Test")
    parser.add_argument("--image", default=None, help="Path to single image. If not provided, webcam is used.")
    parser.add_argument("--onnx-path", default=os.path.join("models", "eye_cnn", "eye_sleepiness.onnx"),
                        help="Path to the ONNX model.")
    parser.add_argument("--window", type=int, default=15, help="Number of frames for temporal smoothing")
    args = parser.parse_args()
    
    if not os.path.isfile(args.onnx_path):
        print(f"ERROR: Model file not found: {args.onnx_path}")
        sys.exit(1)
        
    print("Loading FaceMeshDetector...")
    detector = FaceMeshDetector(max_faces=1)
    print(f"Loading ONNX Model from {args.onnx_path}...")
    sess = ort.InferenceSession(args.onnx_path)
    
    debug_mode = False
    last_print_time = time.time()
    
    # Temporal Smoothing Queue
    # We maintain a short history of Average P(SLEEPY)
    history = collections.deque(maxlen=args.window)
    
    def process_frame(frame, debug, last_time):
        pts_px, _ = detector.process(frame)
        if pts_px is None:
            return frame, last_time
        
        debug_info = []
        
        # Left eye
        left_crop, (x1, y1, x2, y2) = crop_eye(frame, pts_px, LEFT_EYE)
        res_left = {"p_sleepy": 0.0, "label": "NONE", "confidence": 0.0, "p_awake": 0.0}
        if left_crop.size > 0:
            res_left = infer_with_session(sess, left_crop)
            color = (0, 255, 0) if res_left["label"] == "AWAKE" else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            debug_info.append(("LEFT", left_crop, res_left, (x1, y1, x2, y2)))
            
        # Right eye
        right_crop, (rx1, ry1, rx2, ry2) = crop_eye(frame, pts_px, RIGHT_EYE)
        res_right = {"p_sleepy": 0.0, "label": "NONE", "confidence": 0.0, "p_awake": 0.0}
        if right_crop.size > 0:
            res_right = infer_with_session(sess, right_crop)
            color = (0, 255, 0) if res_right["label"] == "AWAKE" else (0, 0, 255)
            cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), color, 2)
            debug_info.append(("RIGHT", right_crop, res_right, (rx1, ry1, rx2, ry2)))
            
        # Calculate Temporal Smoothing
        p_left = res_left["p_sleepy"]
        p_right = res_right["p_sleepy"]
        avg_sleepy = (p_left + p_right) / 2.0
        
        history.append(avg_sleepy)
        smoothed_sleepy = sum(history) / len(history) if history else 0.0
        cnn_state = "SLEEPY" if smoothed_sleepy >= 0.5 else "AWAKE"
        state_color = (0, 0, 255) if cnn_state == "SLEEPY" else (0, 255, 0)
        
        # Draw on Frame
        y_text = 30
        cv2.putText(frame, f"L P(SLEEPY): {p_left:.2f}", (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y_text += 25
        cv2.putText(frame, f"R P(SLEEPY): {p_right:.2f}", (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y_text += 25
        cv2.putText(frame, f"Avg P(SLEEPY): {avg_sleepy:.2f}", (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        y_text += 25
        cv2.putText(frame, f"Smoothed P(SLEEPY): {smoothed_sleepy:.2f}", (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        y_text += 30
        cv2.putText(frame, f"CNN State: {cnn_state}", (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.8, state_color, 2)
        
        # Periodic printing if debug is on (or just print temporal data periodically)
        curr_time = time.time()
        should_print = (curr_time - last_time > 0.5)
        
        if should_print:
            print(f"[{time.strftime('%H:%M:%S')}] L:{p_left:.2f} | R:{p_right:.2f} | Avg:{avg_sleepy:.2f} | Smooth:{smoothed_sleepy:.2f} | STATE: {cnn_state}")
            last_time = curr_time
        
        # Draw debug UI if active
        if debug and debug_info:
            debug_panel_h = 250
            debug_panel_w = 600
            debug_panel = np.zeros((debug_panel_h, debug_panel_w, 3), dtype=np.uint8)
            
            for i, (eye_name, raw_crop, res, rect) in enumerate(debug_info):
                y_offset = i * 120
                
                raw_crop_resized = cv2.resize(raw_crop, (64, 64))
                debug_panel[y_offset:y_offset+64, 10:74] = raw_crop_resized
                
                prep_gray = res['preprocessed']
                prep_bgr = cv2.cvtColor(prep_gray, cv2.COLOR_GRAY2BGR)
                prep_resized = cv2.resize(prep_bgr, (64, 64))
                debug_panel[y_offset:y_offset+64, 90:154] = prep_resized
                
                text_x = 170
                cv2.putText(debug_panel, f"{eye_name} EYE - {res['label']} ({res['confidence']:.2f})", 
                            (text_x, y_offset + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.putText(debug_panel, f"P(AWAKE): {res['p_awake']:.3f} | P(SLEEPY): {res['p_sleepy']:.3f}", 
                            (text_x, y_offset + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                cv2.putText(debug_panel, f"BBox: {rect}", 
                            (text_x, y_offset + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
            cv2.imshow("Debug Panel", debug_panel)
        elif not debug:
            try:
                cv2.destroyWindow("Debug Panel")
            except:
                pass
                
        return frame, last_time

    if args.image:
        frame = cv2.imread(args.image)
        if frame is not None:
            print("Press 'd' to toggle debug view. Press 'q' to quit.")
            while True:
                display_frame = frame.copy()
                display_frame, _ = process_frame(display_frame, debug_mode, last_print_time)
                cv2.imshow("Eye CNN Temporal Test", display_frame)
                key = cv2.waitKey(100) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('d'):
                    debug_mode = not debug_mode
        else:
            print(f"ERROR: Could not read image: {args.image}")
    else:
        print("Starting webcam temporal test...")
        print("Test how the CNN responds to: Open, Partially Closed, Fully Closed, and Blinking.")
        print("Press 'd' to toggle visual debug. Press 'q' to quit.")
        
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame = cv2.flip(frame, 1)
            frame, last_print_time = process_frame(frame, debug_mode, last_print_time)
            
            cv2.imshow("Eye CNN Temporal Test", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('d'):
                debug_mode = not debug_mode
                
        cap.release()
        
    cv2.destroyAllWindows()
    detector.close()

if __name__ == "__main__":
    main()
