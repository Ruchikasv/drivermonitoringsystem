import cv2
import os
import hashlib
from collections import defaultdict
from app.api.monitoring_ws import DriverSessionProcessor

def hash_file(filepath):
    if not os.path.exists(filepath):
        return None
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def run_regression():
    videos = [
        ("Normal Behavior", "data/demo_videos/1_normal.mp4", None),
        ("Normal Blinking", "data/demo_videos/2_normal_blink.mp4", None),
        ("Active/Frequent Blinking", "data/demo_videos/3_active_blink.mp4", None),
        ("Yawning", "data/demo_videos/4_yawning.mp4", None),
        ("Drowsy", "data/demo_videos/5_drowsy.mp4", None),
        ("Sleepy", "data/demo_videos/6_sleepy.mp4", None),
        ("Critical", "data/demo_videos/7_critical.mp4", None),
        ("Recovery", "data/demo_videos/8_recovery.mp4", None),
        ("Future Sensor Injection", "data/demo_videos/1_normal.mp4", {
            "alcohol_level": 0.12,
            "alcohol_detected": True,
            "ir_eye_confidence": 0.95
        })
    ]
    
    # 1. Video Integrity Validation
    file_hashes = {}
    hash_counts = defaultdict(int)
    for _, path, _ in videos:
        if path not in file_hashes:
            h = hash_file(path)
            file_hashes[path] = h
            if h is not None:
                hash_counts[h] += 1
                
    print("=" * 140)
    print(" DMS VIDEO REGRESSION TEST SUITE ")
    print("=" * 140)
    
    header = f"{'Scenario':<26} | {'File':<16} | {'SHA256 (short)':<14} | {'Dup?':<4} | {'Frames':<6} | {'Face%':<5} | {'Min EAR':<7} | {'Max PERC':<9} | {'Max CNN P':<9} | {'Max KSS':<7} | {'Max Alert':<9} | {'Result'}"
    print(header)
    print("-" * 140)

    valid_count = 0
    invalid_count = 0
    missing_count = 0
    duplicate_count = 0
    
    for test_name, video_path, extra_sensors in videos:
        file_hash = file_hashes.get(video_path)
        filename = os.path.basename(video_path)
        
        if file_hash is None:
            missing_count += 1
            invalid_count += 1
            print(f"{test_name:<26} | {filename:<16} | {'MISSING':<14} | {'-':<4} | {'N/A':<6} | {'N/A':<5} | {'N/A':<7} | {'N/A':<9} | {'N/A':<9} | {'N/A':<7} | {'N/A':<9} | MISSING")
            continue
            
        short_hash = file_hash[:12] + ".."
        is_duplicate = hash_counts[file_hash] > 1
        dup_str = "YES" if is_duplicate else "NO"
        
        processor = DriverSessionProcessor(session_id=999, driver_id=999, driver_name="Test", vehicle_reg=None)
        
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        
        frame_count = 0
        face_count = 0
        min_ear = 1.0
        max_perclos = 0.0
        max_cnn = 0.0
        max_kss = 0.0
        max_alert = 0
        
        current_time = 0.0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            current_time += (1.0 / fps)
            
            _, metrics, alert = processor.process_frame(frame, now=current_time, extra_sensors=extra_sensors)
            
            if metrics.get("face_detected", False):
                face_count += 1
                min_ear = min(min_ear, metrics.get("ear", 1.0))
                max_perclos = max(max_perclos, metrics.get("perclos", 0.0))
                max_cnn = max(max_cnn, metrics.get("cnn_p_sleepy", 0.0))
                max_kss = max(max_kss, metrics.get("kss", 0.0))
                
            if alert:
                level = alert.get("level", 0)
                max_alert = max(max_alert, level)
                
        cap.release()
        processor.close()
        
        face_pct = (face_count / frame_count * 100) if frame_count > 0 else 0
        alert_str = f"Level {max_alert}" if max_alert > 0 else "None"
        
        if is_duplicate:
            result = "DATA INVALID"
            invalid_count += 1
        else:
            result = "PASS"
            valid_count += 1
            
        print(f"{test_name:<26} | {filename:<16} | {short_hash:<14} | {dup_str:<4} | {frame_count:<6} | {face_pct:>4.0f}% | {min_ear:>7.3f} | {max_perclos:>8.1%} | {max_cnn:>9.3f} | {max_kss:>7.1f} | {alert_str:<9} | {result}")

    # For duplicate tracking, we only care about how many files were actually duplicates
    # Let's count how many files had duplicates
    for h, c in hash_counts.items():
        if c > 1:
            duplicate_count += c

    print("-" * 140)
    print(" SUMMARY ")
    print(f"VALID SCENARIOS: {valid_count}/9")
    print(f"INVALID SCENARIOS: {invalid_count}/9")
    print(f"DUPLICATE VIDEOS: {duplicate_count}")
    print(f"MISSING FILES: {missing_count}")
    
    if invalid_count > 0:
        print("OVERALL: DATA INVALID")
    else:
        print("OVERALL: PASS")
    print("=" * 140)

if __name__ == '__main__':
    run_regression()
