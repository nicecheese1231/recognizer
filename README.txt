# Attention MVP (Windows 11)

## 1) Python & venv
- Install **Python 3.10+ (64-bit)**.
- Open **Command Prompt (cmd)** or **PowerShell** in this folder.

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> If `mediapipe` install fails, try: `pip install --upgrade pip setuptools wheel` first.

## 2) Run (Webcam)
```bat
python attention_mvp.py --camera 0
```

- If nothing shows, try `--camera 1` or another index.
- For a video file:
```bat
python attention_mvp.py --video path\to\file.mp4
```

## 3) Controls
- **q**: quit
- **s**: toggle telemetry text
- **l**: toggle CSV logging (writes `attention_log.csv`)

## 4) Notes & Tuning
- Adjust `ear_thresh` and `EMA_TARGET` (inside code) to your camera distance and lighting.
- The score is heuristic: gaze offset + eye openness + blink streak. Start simple, then iterate.
- Later, you can add a tiny temporal head (TCN/GRU) using pseudo labels from this score.
