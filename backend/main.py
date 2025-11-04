# backend/main.py
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import subprocess
import sys
import os
import threading
import time
import csv
import re
import glob
from typing import Optional, List, Dict, Any

app = FastAPI(title="AI Attention Backend", version="3.1")

# --- CORS (프론트: Vite 5173 포트) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.join(BASE_DIR, "scripts")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def script_path() -> str:
    """attention_mvp.py 절대 경로"""
    return os.path.join(SCRIPT_DIR, "attention_mvp.py")


@app.get("/health")
def health():
    return {
        "ok": True,
        "script_exists": os.path.exists(script_path()),
        "log_dir": LOG_DIR,
    }


# ===================== attention_mvp 실행 & 로그 저장 =====================

# attention_mvp.py 한 줄 예:
# t=0.12 score=85.23 ear=0.250 gaze_h=0.032 gaze_v=0.020
LINE_RE = re.compile(
    r"score=(?P<score>[-0-9.]+).*ear=(?P<ear>[-0-9.]+).*gaze_h=(?P<gaze_h>[-0-9.]+).*gaze_v=(?P<gaze_v>[-0-9.]+)"
)


def parse_line(line: str) -> Optional[Dict[str, str]]:
    """stdout 한 줄에서 score/ear/gaze 값 추출"""
    m = LINE_RE.search(line)
    if not m:
        return None
    return {
        "score": m.group("score"),
        "ear": m.group("ear"),
        "gaze_h": m.group("gaze_h"),
        "gaze_v": m.group("gaze_v"),
    }


@app.post("/run-attention")
def run_attention(
    id: Optional[str] = Body(None),
    title: Optional[str] = Body(None),
    start: Optional[str] = Body(None),
    isOnline: bool = Body(False),
    camera: int = Body(0),
    video: Optional[str] = Body(None),
):
    """
    프론트에서 호출해서 attention_mvp.py 실행
    - stdout을 읽어 backend/logs/run_*.csv 로 저장
    """
    spath = script_path()
    if not os.path.exists(spath):
        return {"status": "error", "message": f"Script not found: {spath}"}

    # 실행마다 고유 run_id 생성 (timestamp 기반)
    run_id = f"run_{int(time.time())}"
    log_path = os.path.join(LOG_DIR, f"{run_id}.csv")

    # CSV 헤더 생성
    try:
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ts", "score", "ear", "gaze_h", "gaze_v"])
    except Exception as e:
        return {"status": "error", "message": f"Failed to create log file: {e}"}

    # attention_mvp.py 인자
    args = [sys.executable, spath]
    if video:
        args += ["--video", video]
    else:
        args += ["--camera", str(camera)]

    # 영상창: 오른쪽 아래 작게, 항상 위
    args += [
        "--win-width",
        "480",
        "--win-height",
        "270",
        "--win-pos",
        "bottom-right",
        "--always-on-top",
    ]

    # 컨트롤 창 (START / PAUSE / QUIT, 항상 위)
    args += ["--control-window", "--control-topmost"]

    try:
        proc = subprocess.Popen(
            args,
            cwd=SCRIPT_DIR,  # scripts 폴더 기준 실행
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as e:
        return {"status": "error", "message": f"Failed to start script: {e}"}

    # stdout → CSV 저장 쓰레드
    def reader_thread():
        try:
            with open(log_path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                for line in proc.stdout or []:
                    line = line.strip()
                    parsed = parse_line(line)
                    if not parsed:
                        continue
                    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    w.writerow(
                        [
                            ts,
                            parsed["score"],
                            parsed["ear"],
                            parsed["gaze_h"],
                            parsed["gaze_v"],
                        ]
                    )
                    f.flush()
        except Exception as e:
            print(f"[reader_thread ERROR] {e}", flush=True)

    t = threading.Thread(target=reader_thread, daemon=True)
    t.start()

    meta = {
        "run_id": run_id,
        "title": title,
        "start": start,
        "isOnline": isOnline,
        "log_path": log_path,
    }
    return {"status": "ok", "message": "attention_mvp launched", "meta": meta}


# ===================== 로그 조회 유틸 =====================


def list_log_files() -> List[str]:
    """logs 폴더 안의 csv 목록 (최신순)"""
    paths = glob.glob(os.path.join(LOG_DIR, "*.csv"))
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths


def read_latest_row_from_csv(path: str) -> Optional[Dict[str, Any]]:
    """
    해당 csv에서 마지막 '유효한' 데이터 행 하나 읽어서 반환
    - 빈 줄/헤더는 건너뜀
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        # 뒤에서부터 훑으면서 데이터 행 찾기
        for row in reversed(rows):
            if len(row) < 5:
                continue
            if row[0].strip().lower() == "ts":
                # 헤더
                continue
            ts, score, ear, gh, gv = row[:5]
            return {
                "ts": ts.strip(),
                "score": score.strip(),
                "ear": ear.strip(),
                "gaze_h": gh.strip(),
                "gaze_v": gv.strip(),
            }

        return None
    except Exception as e:
        print(f"[read_latest_row_from_csv ERROR] {e}", flush=True)
        return None


# ===================== 엔드포인트: 실행 목록 & 최신 샘플 =====================

@app.get("/logs")
def list_logs():
    """
    저장된 실행(run) 목록 반환
    - run_id, created_at 등
    """
    files = list_log_files()
    data = []
    for p in files:
        name = os.path.basename(p)
        run_id = name.replace(".csv", "")
        created = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p))
        )
        data.append(
            {
                "id": run_id,
                "title": run_id,
                "start": None,
                "isOnline": None,
                "created_at": created,
            }
        )
    return JSONResponse({"status": "ok", "data": data})


@app.get("/logs/latest")
def latest_any():
    """
    가장 최근 실행(run)의 마지막 샘플 1개 반환
    - 실행 선택 안 했을 때(최신 라이브 모드)에 사용
    """
    files = list_log_files()
    if not files:
        return JSONResponse({"status": "ok", "data": None})
    latest_path = files[0]
    row = read_latest_row_from_csv(latest_path)
    if not row:
        return JSONResponse({"status": "ok", "data": None})
    return JSONResponse({"status": "ok", "data": row})


@app.get("/logs/{run_id}/latest")
def latest_for_run(run_id: str):
    """
    특정 실행(run_id)의 마지막 샘플 1개 반환
    - 실행 목록에서 골랐을 때 사용
    """
    path = os.path.join(LOG_DIR, f"{run_id}.csv")
    if not os.path.exists(path):
        return JSONResponse(
            {"status": "error", "message": f"log not found for run_id={run_id}"},
            status_code=404,
        )
    row = read_latest_row_from_csv(path)
    if not row:
        return JSONResponse({"status": "ok", "data": None})
    return JSONResponse({"status": "ok", "data": row})
