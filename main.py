from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
import logging
import time
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
    description="Backend for music streaming (WORKING VERSION)",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ YouTube DL Options ------------------
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
    "cookiefile": "cookies.txt",
    "verbose": True,
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.youtube.com/",
    },
}


# ------------------ Cache ------------------
class AudioCache:
    def __init__(self, max_size: int = 100, ttl: int = 1800):
        self.cache: Dict[str, dict] = {}
        self.max_size = max_size
        self.ttl = ttl

    def get(self, video_id: str) -> Optional[dict]:
        if video_id in self.cache:
            entry = self.cache[video_id]
            if time.time() - entry["timestamp"] < self.ttl:
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
        "usage": "Use /play/VIDEO_ID to get audio URL or /redirect/VIDEO_ID to play directly",
        "example": "http://localhost:8000/play/dQw4w9WgXcQ"
    }

@app.get("/play/{video_id}")
def get_audio_url(video_id: str):
    """Get audio URL that works in browsers"""
    try:
        # Check cache first
        cached = audio_cache.get(video_id)
        if cached:
            return JSONResponse(content={**cached, "cached": True})

        logger.info(f"Fetching audio URL for: {video_id}")
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="Video not found")
            
            # Get the best audio URL
            audio_url = info.get('url')
            formats = info.get('formats', [])
            
            # If no direct URL, find the best audio format
            if not audio_url and formats:
                # Look for audio-only formats
                audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_formats:
                    # Sort by bitrate (highest first)
                    audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                    audio_url = audio_formats[0].get('url')
                else:
                    # Fallback to any format with audio
                    for f in formats:
                        if f.get('acodec') != 'none':
                            audio_url = f.get('url')
                            break
            
            if not audio_url:
                raise HTTPException(status_code=404, detail="No audio stream found")
            
            # Prepare response
            result = {
                "video_id": video_id,
                "title": info.get('title', 'Unknown Title'),
                "artist": info.get('uploader', 'Unknown Artist'),
                "duration": info.get('duration', 0),
                "audio_url": audio_url,
                "thumbnail": info.get('thumbnail'),
                "webpage_url": info.get('webpage_url'),
                "success": True,
                "message": "Copy the audio_url and paste in browser address bar to play"
            }
            
            # Cache the result
            audio_cache.set(video_id, result)
            
            return JSONResponse(content={**result, "cached": False})
            
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get audio: {str(e)}")

@app.get("/redirect/{video_id}")
def redirect_to_audio(video_id: str):
    """Redirect directly to audio stream (BEST FOR BROWSER PLAYBACK)"""
    try:
        logger.info(f"Redirecting to audio for: {video_id}")
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="Video not found")
            
            audio_url = info.get('url')
            formats = info.get('formats', [])
            
            # Find best audio URL
            if not audio_url and formats:
                audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_formats:
                    audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                    audio_url = audio_formats[0].get('url')
            
            if not audio_url:
                raise HTTPException(status_code=404, detail="No audio stream found")
            
            # Redirect to the audio URL
            response = RedirectResponse(url=audio_url)
            
            # Add headers that YouTube expects
            response.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            response.headers["Referer"] = "https://www.youtube.com/"
            response.headers["Origin"] = "https://www.youtube.com"
            
            return response
            
    except Exception as e:
        logger.error(f"Redirect error: {e}")
        raise HTTPException(status_code=500, detail=f"Redirect failed: {str(e)}")

@app.get("/test/{video_id}")
def test_playback(video_id: str):
    """Simple test endpoint that returns HTML to play audio"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Audio Player</title>
    </head>
    <body>
        <h1>YouTube Audio Player Test</h1>
        <p>Video ID: {video_id}</p>
        <audio controls autoplay style="width: 100%;">
            <source src="/redirect/{video_id}" type="audio/mp4">
            Your browser does not support the audio element.
        </audio>
        <br><br>
        <a href="/redirect/{video_id}" target="_blank">Direct Audio Link</a>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)

# ------------------ START THE SERVER ------------------
if __name__ == "__main__":
    import uvicorn
    import os
    print("🧠 Cookie file exists:", os.path.exists("cookies.txt"))
    print("🎵 YouTube Music API Starting...")
    print("📢 Use these URLs in your browser:")
    print("   http://localhost:8000/play/dQw4w9WgXcQ")
    print("   http://localhost:8000/redirect/dQw4w9WgXcQ")
    print("   http://localhost:8000/test/dQw4w9WgXcQ")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")




