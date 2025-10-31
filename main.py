from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
import logging
import time
import os
from typing import Dict, Optional

# ------------------ Logging ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("YouTubeMusicAPI")

# ------------------ App Setup ------------------
app = FastAPI(
    title="YouTube Music API",
    description="Backend for music streaming (Render-safe version)",
    version="3.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ YouTube DL Options ------------------
COOKIE_FILE = os.getenv("COOKIES_FILE", "cookies.txt")

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": False,
    "noplaylist": True,
    "extractaudio": True,
    "audioformat": "mp3",
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "no_warnings": False,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "forceip": 4,
    # ✅ Add cookies if file exists (Render-safe)
    **({"cookiefile": COOKIE_FILE} if os.path.exists(COOKIE_FILE) else {}),
    # Optional: set proxy if YouTube blocks datacenter IPs
    # "proxy": os.getenv("YTDLP_PROXY", "http://username:password@proxyhost:port"),
}

# ------------------ Cache ------------------
class AudioCache:
    def __init__(self, max_size: int = 100, ttl: int = 1800):
        self.cache: Dict[str, dict] = {}
        self.max_size = max_size
        self.ttl = ttl

    def get(self, video_id: str) -> Optional[dict]:
        entry = self.cache.get(video_id)
        if entry and time.time() - entry["timestamp"] < self.ttl:
            return entry["data"]
        return None

    def set(self, video_id: str, data: dict):
        if len(self.cache) >= self.max_size:
            self.cache.pop(next(iter(self.cache)))
        self.cache[video_id] = {"data": data, "timestamp": time.time()}

audio_cache = AudioCache()

# ------------------ ROUTES ------------------

@app.get("/")
def root():
    return {
        "message": "YouTube Music API is RUNNING!",
        "usage": "Use /play/VIDEO_ID or /redirect/VIDEO_ID",
        "example": "https://your-app.onrender.com/play/dQw4w9WgXcQ"
    }

@app.get("/play/{video_id}")
def get_audio_url(video_id: str):
    """Fetch and return direct audio URL"""
    try:
        cached = audio_cache.get(video_id)
        if cached:
            return JSONResponse(content={**cached, "cached": True})

        logger.info(f"Fetching audio for video: {video_id}")
        url = f"https://www.youtube.com/watch?v={video_id}"

        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise HTTPException(status_code=404, detail="Video not found")

        formats = info.get("formats", [])
        audio_url = info.get("url")

        if not audio_url and formats:
            audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            if audio_formats:
                audio_formats.sort(key=lambda x: x.get("abr", 0) or 0, reverse=True)
                audio_url = audio_formats[0].get("url")

        if not audio_url:
            raise HTTPException(status_code=404, detail="No audio stream found")

        result = {
            "video_id": video_id,
            "title": info.get("title", "Unknown Title"),
            "artist": info.get("uploader", "Unknown Artist"),
            "duration": info.get("duration", 0),
            "audio_url": audio_url,
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url"),
            "success": True,
        }

        audio_cache.set(video_id, result)
        return JSONResponse(content={**result, "cached": False})

    except Exception as e:
        logger.error(f"Error fetching audio: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch audio: {e}")

@app.get("/redirect/{video_id}")
def redirect_to_audio(video_id: str):
    """Redirect directly to audio stream"""
    try:
        logger.info(f"Redirecting for video: {video_id}")
        url = f"https://www.youtube.com/watch?v={video_id}"

        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise HTTPException(status_code=404, detail="Video not found")

        audio_url = info.get("url")
        formats = info.get("formats", [])

        if not audio_url and formats:
            audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            if audio_formats:
                audio_formats.sort(key=lambda x: x.get("abr", 0) or 0, reverse=True)
                audio_url = audio_formats[0].get("url")

        if not audio_url:
            raise HTTPException(status_code=404, detail="No audio stream found")

        response = RedirectResponse(url=audio_url)
        response.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.youtube.com/",
            "Origin": "https://www.youtube.com"
        })
        return response

    except Exception as e:
        logger.error(f"Redirect error: {e}")
        raise HTTPException(status_code=500, detail=f"Redirect failed: {e}")

@app.get("/test/{video_id}")
def test_playback(video_id: str):
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>YouTube Audio Player</title></head>
    <body>
        <h1>Testing Audio: {video_id}</h1>
        <audio controls autoplay style="width: 100%;">
            <source src="/redirect/{video_id}" type="audio/mp4">
        </audio>
        <p><a href="/redirect/{video_id}" target="_blank">Open Direct Link</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

# ------------------ RUN ------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")
