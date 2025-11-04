#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
attention_mvp.py (100-cap option, stable gauge, control window)
- Webcam or video file
- MediaPipe FaceMesh (refine_landmarks=True)
- EAR / Gaze / Attention Score (0~100)
- EMA smoothing + slew-limit + warm-up ramp (can be disabled via --start-100)
- Face-present hysteresis (플리커 억제)
- 개인 EAR 칼리브레이션(자동 2초, 기본값보다 높아지지 않게 완화)
- Gaze 데드존 확장 + '완벽 자세' 보너스(최대치 쉽게 도달)
- On-screen HUD; optional CSV logging; stdout telemetry
Usage:
  python attention_mvp.py --camera 0 --control-window --always-on-top
  python attention_mvp.py --video path/to/file.mp4 --win-pos bottom-right
  (시작부터 100으로 시작): --start-100
Keys:
  q: quit,  s: toggle text,  l: toggle logging
"""
import argparse
import csv
import time
import platform
import ctypes
import threading
from dataclasses import dataclass

import cv2
import numpy as np

# ---- mediapipe import ----
try:
    import mediapipe as mp
except Exception as e:
    raise SystemExit(
        "Failed to import mediapipe. Install dependencies first:\n"
        "  python -m pip install mediapipe opencv-python numpy\n"
        f"Original error: {e}"
    )

WIN_NAME = "Attention MVP"

# ------------------------ Config ------------------------
@dataclass
class Config:
    fps_sample: int = 10
    ema_alpha: float = 0.30
    ear_thresh: float = 0.21
    blink_streak_max: int = 10
    show_text: bool = True
    log_csv: bool = False
    csv_path: str = "attention_log.csv"

CFG = Config()

# ===== 튜닝 =====
# Calibration (personal EAR target)
CALIB_SECONDS       = 2.0
EAR_TARGET_DEFAULT  = 0.25
EAR_TARGET_MIN      = 0.20   
EAR_TARGET_MAX      = 0.30
# Gaze deadzone (micro-jitter ignore)
GAZE_DEADZONE_X     = 0.10   
GAZE_DEADZONE_Y     = 0.08
# Warm-up ramp (face reacquired)
WARMUP_SECONDS      = 1.5
WARMUP_START_SCORE  = 40.0
WARMUP_END_SCORE    = 100.0
# Slew-rate limit (per processing step)
MAX_RISE_PER_STEP   = 2.5   
MAX_FALL_PER_STEP   = 100.0
# Face presence hysteresis (플리커 억제)
FACE_HIT_CONSEC     = 3     
FACE_MISS_CONSEC    = 6      # 6 연속 미감지 시 absent로

# 런타임 상태
EAR_TARGET_CAL = None
_cal_running = False
_cal_t0 = 0.0
_cal_ears = []

_face_present = False
_face_present_prev = False
_face_hits = 0
_face_misses = 0

_warmup_active = False
_warmup_t0 = 0.0

# -------------------- Landmark indices ------------------
LEFT_EYE  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_IRIS = [468, 469, 470, 471]
LEFT_IRIS  = [472, 473, 474, 475]

# ===== 창 제어 =====
def get_screen_size():
    try:
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return 1920, 1080

def compute_window_pos(pos_str: str, win_w: int, win_h: int):
    sw, sh = get_screen_size()
    margin = 16
    ps = (pos_str or "").lower().replace(" ", "")
    if ps in ("br","bottom-right","right-bottom"):
        return max(0, sw - win_w - margin), max(0, sh - win_h - margin)
    if ps in ("bl","bottom-left","left-bottom"):
        return margin, max(0, sh - win_h - margin)
    if ps in ("tr","top-right","right-top"):
        return max(0, sw - win_w - margin), margin
    if ps in ("tl","top-left","left-top"):
        return margin, margin
    try:
        x_str, y_str = ps.split(",")
        return int(x_str), int(y_str)
    except Exception:
        return max(0, sw - win_w - margin), max(0, sh - win_h - margin)

def set_topmost_window(win_name: str, topmost: bool = True):
    if platform.system() != "Windows":
        return
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, win_name)
        if not hwnd:
            return
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        flags = SWP_NOSIZE | SWP_NOMOVE
        user32.SetWindowPos(hwnd, HWND_TOPMOST if topmost else HWND_NOTOPMOST,
                            0, 0, 0, 0, flags)
    except Exception:
        pass

# ===== 조작창 (Tkinter) =====
class ControlUI(threading.Thread):
    def __init__(self, running_event: threading.Event, stop_event: threading.Event, topmost: bool = True):
        super().__init__(daemon=True)
        self.running_event = running_event
        self.stop_event = stop_event
        self.topmost = topmost

    def run(self):
        try:
            import tkinter as tk
        except Exception:
            return
        root = tk.Tk()
        root.title("Attention Control")
        w, h = 300, 120
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - w)//2
        y = int(sh*0.08)
        root.geometry(f"{w}x{h}+{x}+{y}")
        if self.topmost:
            root.attributes("-topmost", True)
        root.configure(bg="#1e1e1e")

        status = tk.Label(root, text="Paused", font=("Segoe UI", 11), bg="#1e1e1e", fg="#eeeeee")
        status.pack(pady=6)
        btn_frame = tk.Frame(root, bg="#1e1e1e"); btn_frame.pack(pady=4)

        def on_start(): self.running_event.set()
        def on_pause(): self.running_event.clear()
        def on_quit():
            self.stop_event.set()
            try: root.destroy()
            except: pass

        style = dict(font=("Segoe UI", 10, "bold"), fg="white")
        tk.Button(btn_frame, text="START", width=9, command=on_start, bg="#3ba55d", **style).grid(row=0, column=0, padx=4)
        tk.Button(btn_frame, text="PAUSE", width=9, command=on_pause, bg="#faa61a", **style).grid(row=0, column=1, padx=4)
        tk.Button(btn_frame, text="QUIT",  width=9, command=on_quit,  bg="#cc3d3d", **style).grid(row=0, column=2, padx=4)

        def tick():
            status.configure(text="Running" if self.running_event.is_set() else "Paused")
            if self.stop_event.is_set():
                try: root.destroy()
                except: pass
                return
            root.after(200, tick)
        tick()
        root.protocol("WM_DELETE_WINDOW", on_quit)
        root.mainloop()

# ===== 비전 헬퍼 =====
def pts_from_landmarks(landmarks, image_shape, indices):
    h, w = image_shape[:2]
    pts = []
    for idx in indices:
        lm = landmarks[idx]
        pts.append((int(lm.x * w), int(lm.y * h)))
    return np.array(pts, dtype=np.int32)

def ear(eye_pts):
    p1, p2, p3, p4, p5, p6 = eye_pts.astype(np.float32)
    A = np.linalg.norm(p2 - p6)
    B = np.linalg.norm(p3 - p5)
    C = np.linalg.norm(p1 - p4)
    if C < 1e-6:
        return 0.0
    return float((A + B) / (2.0 * C))

def center_of(pts):
    return np.mean(pts.astype(np.float32), axis=0)

def clamp01(x):
    return max(0.0, min(1.0, float(x)))

def gaze_offset_for_eye(eye_pts, iris_pts):
    p1, p4 = eye_pts[0], eye_pts[3]
    eye_w = np.linalg.norm(p1 - p4)
    if eye_w < 1e-6:
        return 0.0, 0.0
    eye_c  = center_of(eye_pts)
    iris_c = center_of(iris_pts)
    dx = (iris_c[0] - eye_c[0]) / eye_w
    dy = (iris_c[1] - eye_c[1]) / eye_w
    if abs(dx) < GAZE_DEADZONE_X: dx = 0.0
    if abs(dy) < GAZE_DEADZONE_Y: dy = 0.0
    off_x = clamp01(abs(dx) / 0.5)
    off_y = clamp01(abs(dy) / 0.4)
    return off_x, off_y

# ===== 스코어 로직 =====
def attention_score(gaze_h, gaze_v, ear_val, blink_streak, a=0.8, b=0.6, c=1.0, d=1.2):
    # 개인 타깃이 기본값보다 높아지지 않게 (상시 감점 방지)
    cal = EAR_TARGET_CAL if EAR_TARGET_CAL is not None else EAR_TARGET_DEFAULT
    ear_target = min(EAR_TARGET_DEFAULT, cal)

    s = 100.0
    s -= a * clamp01(gaze_h) * 40.0
    s -= b * clamp01(gaze_v) * 25.0
    s -= c * max(0.0, (ear_target - max(0.0, ear_val))) * 40.0 / max(ear_target, 1e-6)
    s -= d * clamp01(blink_streak/10.0) * 10.0

    s = float(max(0.0, min(100.0, s)))

    # '완벽 자세' 보너스: 시선 거의 0, 깜박임 0, EAR 충분 → 상한을 98까지 끌어올림
    if gaze_h < 0.02 and gaze_v < 0.02 and blink_streak == 0 and ear_val >= (ear_target - 0.01):
        s = max(s, 98.0)

    return s

def draw_hud(frame, score, ear_val, gaze_h, gaze_v):
    h, w = frame.shape[:2]
    bar_w = int(w * 0.25)
    bar_h = 18
    x0, y0 = 20, 20
    cv2.rectangle(frame, (x0, y0), (x0+bar_w, y0+bar_h), (60,60,60), 1)
    fill = int(bar_w * (score/100.0))
    cv2.rectangle(frame, (x0, y0), (x0+fill, y0+bar_h),
                  (0,180,0) if score>=70 else (0,200,255) if score>=40 else (0,0,255), -1)
    cv2.putText(frame, f"Attention: {score:5.1f}", (x0, y0-5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)
    if CFG.show_text:
        cv2.putText(frame, f"EAR={ear_val:.3f}", (x0, y0+bar_h+22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,200), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Gaze(h,v)=({gaze_h:.2f},{gaze_v:.2f})",
                    (x0, y0+bar_h+45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,200), 1, cv2.LINE_AA)

def slew_limit(prev: float, target: float, rise: float, fall: float):
    if target > prev:
        return min(target, prev + rise)
    else:
        return max(target, prev - fall)

# ===== 메인 =====
def main():
    global EAR_TARGET_CAL, _cal_running, _cal_t0, _cal_ears
    global _face_present, _face_present_prev, _face_hits, _face_misses
    global _warmup_active, _warmup_t0

    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--camera", type=int)
    src.add_argument("--video", type=str)

    # 영상창
    ap.add_argument("--win-width", type=int, default=480)
    ap.add_argument("--win-height", type=int, default=270)
    ap.add_argument("--win-pos", type=str, default="bottom-right")
    ap.add_argument("--always-on-top", action="store_true")

    # 조작창
    ap.add_argument("--control-window", action="store_true")
    ap.add_argument("--control-topmost", action="store_true")

    # 처리
    ap.add_argument("--fps", type=int, default=CFG.fps_sample)
    ap.add_argument("--log", action="store_true")

    # 새 옵션: 시작부터 100
    ap.add_argument("--start-100", action="store_true",
                    help="Start gauge at 100 and disable warm-up capping")

    args = ap.parse_args()
    CFG.log_csv = bool(args.log)

    # 소스 오픈 (CAP_DSHOW 문제 시 백엔드 제거)
    if args.camera is not None:
        try:
            cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(args.camera)
        except Exception:
            cap = cv2.VideoCapture(args.camera)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    else:
        cap = cv2.VideoCapture(args.video)

    if not cap.isOpened():
        raise SystemExit("Camera/Video open failed. Use --camera 0 or valid --video path.")

    # 영상창 강제 생성/배치
    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_NAME, args.win_width, args.win_height)
    x, y = compute_window_pos(args.win_pos, args.win_width, args.win_height)
    cv2.moveWindow(WIN_NAME, x, y)
    if args.always_on_top:
        set_topmost_window(WIN_NAME, True)

    # MediaPipe
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True,
                                      min_detection_confidence=0.5,
                                      min_tracking_confidence=0.5)

    # 상태
    ema_score    = 100.0 if args.start_100 else float(WARMUP_START_SCORE)
    blink_streak = 0
    was_closed   = False

    # 조작창 이벤트
    running_event = threading.Event()
    stop_event    = threading.Event()
    if args.control_window:
        running_event.clear()
        ControlUI(running_event, stop_event, topmost=args.control_topmost).start()
    else:
        running_event.set()

    # 타이밍
    proc_fps = max(1, int(args.fps))
    last_t = time.time()

    # CSV
    csv_writer = None
    csv_file = None
    if CFG.log_csv:
        csv_file = open(CFG.csv_path, "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["ts", "score", "ear", "gaze_h", "gaze_v"])

    start_t = time.time()

    # 초기화
    EAR_TARGET_CAL = None
    _cal_running = False
    _cal_t0 = 0.0
    _cal_ears = []

    _face_present = False
    _face_present_prev = False
    _face_hits = 0
    _face_misses = 0

    _warmup_active = False
    _warmup_t0 = 0.0

    try:
        while True:
            if stop_event.is_set():
                break

            ret, frame = cap.read()
            if not ret:
                break

            now = time.time()
            do_process = (now - last_t) >= (1.0 / proc_fps)

            # 일시정지 상태 UI
            if not running_event.is_set():
                cv2.putText(frame, "Paused - click START in control window",
                            (20, frame.shape[0]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                            (0,255,255), 1, cv2.LINE_AA)
                cv2.imshow(WIN_NAME, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            if do_process:
                last_t = now
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = face_mesh.process(rgb)

                ear_val = 0.0; gaze_h = 0.0; gaze_v = 0.0

                if res.multi_face_landmarks:
                    # ----- 히트/미스 누적 (hysteresis) -----
                    _face_hits  = min(FACE_HIT_CONSEC, _face_hits + 1)
                    _face_misses = 0
                    prev_present = _face_present
                    _face_present = (_face_hits >= FACE_HIT_CONSEC)
                    if _face_present and not prev_present:
                        _warmup_active = True
                        _warmup_t0 = now
                        # 시작부터 100 모드일 땐 웜업 클램프 비활성화
                        if not args.start_100:
                            ema_score = min(ema_score, WARMUP_START_SCORE)

                    lm = res.multi_face_landmarks[0].landmark
                    leye = pts_from_landmarks(lm, frame.shape, LEFT_EYE)
                    reye = pts_from_landmarks(lm, frame.shape, RIGHT_EYE)
                    ear_val = (ear(leye) + ear(reye)) * 0.5

                    l_iris = pts_from_landmarks(lm, frame.shape, LEFT_IRIS)
                    r_iris = pts_from_landmarks(lm, frame.shape, RIGHT_IRIS)
                    gx_l, gy_l = gaze_offset_for_eye(leye, l_iris)
                    gx_r, gy_r = gaze_offset_for_eye(reye, r_iris)
                    gaze_h = float((gx_l + gx_r) * 0.5)
                    gaze_v = float((gy_l + gy_r) * 0.5)

                    # --- Calibration (정면 응시일 때만 누적)
                    if EAR_TARGET_CAL is None and not _cal_running:
                        _cal_running = True; _cal_t0 = now; _cal_ears.clear()
                    if _cal_running:
                        if gaze_h == 0.0 and gaze_v == 0.0:
                            _cal_ears.append(float(ear_val))
                        if (now - _cal_t0) >= CALIB_SECONDS:
                            if _cal_ears:
                                m = float(np.median(_cal_ears))
                                m = max(EAR_TARGET_MIN, min(EAR_TARGET_MAX, m))
                                # 기본값보다 높게는 잡지 않음
                                EAR_TARGET_CAL = min(EAR_TARGET_DEFAULT, m)
                            _cal_running = False

                    # --- Blink streak
                    if ear_val < CFG.ear_thresh:
                        if was_closed:
                            blink_streak = min(CFG.blink_streak_max, blink_streak + 1)
                        else:
                            was_closed = True; blink_streak = 1
                    else:
                        was_closed = False
                        blink_streak = max(0, blink_streak - 2)

                    # --- Raw score
                    raw = attention_score(gaze_h, gaze_v, ear_val, blink_streak)

                    # --- EMA target + warm-up 상한(타깃에 적용)
                    ema_target = (1.0 - CFG.ema_alpha) * ema_score + CFG.ema_alpha * raw
                    if _warmup_active and not args.start_100:
                        t = now - _warmup_t0
                        if t >= WARMUP_SECONDS:
                            _warmup_active = False
                        else:
                            allow = WARMUP_START_SCORE + (WARMUP_END_SCORE - WARMUP_START_SCORE) * (t / WARMUP_SECONDS)
                            ema_target = min(ema_target, allow)

                    # --- Slew-limit toward target
                    ema_score = slew_limit(ema_score, ema_target, MAX_RISE_PER_STEP, MAX_FALL_PER_STEP)

                    # draw
                    for p in np.concatenate([leye, reye, l_iris, r_iris], axis=0):
                        cv2.circle(frame, tuple(p), 1, (0, 255, 255), -1)
                    draw_hud(frame, ema_score, ear_val, gaze_h, gaze_v)

                    # 상태 텍스트
                    if _cal_running:
                        cv2.putText(frame, "Calibrating... look straight & keep eyes open",
                                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,0), 1, cv2.LINE_AA)
                    elif EAR_TARGET_CAL is not None:
                        cv2.putText(frame, f"EAR target={EAR_TARGET_CAL:.3f}",
                                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180,180,180), 1, cv2.LINE_AA)
                    if _warmup_active and not args.start_100:
                        cv2.putText(frame, "Warming up...",
                                    (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,200,255), 1, cv2.LINE_AA)

                else:
                    # ----- miss 누적 (hysteresis) -----
                    _face_misses = min(FACE_MISS_CONSEC, _face_misses + 1)
                    _face_hits = 0
                    prev_present = _face_present
                    _face_present = not (_face_misses >= FACE_MISS_CONSEC)

                    if not _face_present:
                        ema_score = max(0.0, ema_score - 1.5)
                        draw_hud(frame, ema_score, 0.0, 0.0, 0.0)
                        cv2.putText(frame, "No face detected", (20, frame.shape[0]-20),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,140,255), 1, cv2.LINE_AA)

                # telemetry/logging
                t_sec = time.time() - start_t
                print(f"t={t_sec:.2f} score={ema_score:.2f} ear={ear_val:.3f} gaze_h={gaze_h:.3f} gaze_v={gaze_v:.3f}", flush=True)
                if CFG.log_csv and csv_writer:
                    csv_writer.writerow([f"{time.time():.3f}", f"{ema_score:.3f}", f"{ear_val:.4f}", f"{gaze_h:.4f}", f"{gaze_v:.4f}"])

            # footer & key
            cv2.putText(frame, "[q] quit  [s] toggle text  [l] toggle logging",
                        (20, frame.shape[0]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230,230,230), 1, cv2.LINE_AA)
            cv2.imshow(WIN_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                CFG.show_text = not CFG.show_text
            elif key == ord('l'):
                if not CFG.log_csv and csv_writer is None:
                    csv_file = open(CFG.csv_path, "w", newline="", encoding="utf-8")
                    csv_writer = csv.writer(csv_file)
                    csv_writer.writerow(["ts", "score", "ear", "gaze_h", "gaze_v"])
                CFG.log_csv = not CFG.log_csv

            _face_present_prev = _face_present

    finally:
        try:
            if csv_file: csv_file.close()
        except Exception:
            pass
        try:
            face_mesh.close()
        except Exception:
            pass
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
