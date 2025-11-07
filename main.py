from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
import logging
import time
import random
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
    description="Backend for music streaming with enhanced error handling",
    version="4.0.0"
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
    "ignoreerrors": False,
    "no_warnings": False,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "forceip": 4,
    # Enhanced options for cloud deployment
    "cookiefile": os.getenv("COOKIES_FILE", "cookies.txt"),
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "player_skip": ["configs", "webpage"]
        }
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-us,en;q=0.5",
        "Accept-Encoding": "gzip,deflate",
        "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
        "Connection": "keep-alive",
    }
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

# ------------------ Enhanced Helper Functions ------------------

def get_audio_url_with_retry(video_id: str, max_retries: int = 3):
    """Get audio URL with retry logic and rotating user agents"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0"
    ]
    
    for attempt in range(max_retries):
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Rotate user agents and create custom options for each attempt
            current_ydl_opts = YDL_OPTS.copy()
            current_ydl_opts["http_headers"]["User-Agent"] = random.choice(user_agents)
            
            # Add progressive backoff
            if attempt > 0:
                current_ydl_opts["extractor_args"]["youtube"]["player_client"] = ["tv", "web"]
            
            logger.info(f"Attempt {attempt + 1} for {video_id} with {current_ydl_opts['http_headers']['User-Agent'][:50]}...")
            
            with YoutubeDL(current_ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info and (info.get('url') or info.get('formats')):
                    logger.info(f"Successfully fetched info for {video_id} on attempt {attempt + 1}")
                    return info
                else:
                    logger.warning(f"No valid info returned for {video_id} on attempt {attempt + 1}")
                
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for {video_id}: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"Waiting {wait_time:.2f} seconds before retry...")
                time.sleep(wait_time)
            else:
                logger.error(f"All {max_retries} attempts failed for {video_id}")
    
    return None

def get_audio_from_alternative_sources(video_id: str):
    """Try alternative YouTube frontends if main site fails"""
    alternative_instances = [
        f"https://yewtu.be/watch?v={video_id}",      # Invidious
        f"https://piped.video/watch?v={video_id}",   # Piped
        f"https://inv.riverside.rocks/watch?v={video_id}",  # Another Invidious
        f"https://piped-api.kavin.rocks/watch?v={video_id}", # Piped API
    ]
    
    logger.info(f"Trying alternative sources for {video_id}")
    
    for alt_url in alternative_instances:
        try:
            logger.info(f"Trying alternative: {alt_url}")
            with YoutubeDL(YDL_OPTS) as ydl:
                info = ydl.extract_info(alt_url, download=False)
                if info and (info.get('url') or info.get('formats')):
                    logger.info(f"Success with alternative source: {alt_url}")
                    return info
        except Exception as e:
            logger.warning(f"Alternative source failed {alt_url}: {str(e)}")
            continue
    
    return None

def extract_best_audio_url(info: dict) -> Optional[str]:
    """Extract the best available audio URL from info dict"""
    if not info:
        return None
    
    # Try direct URL first
    audio_url = info.get('url')
    if audio_url:
        return audio_url
    
    # If no direct URL, find best audio format
    formats = info.get('formats', [])
    if not formats:
        return None
    
    # Prefer audio-only formats
    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
    
    if audio_formats:
        # Sort by bitrate (highest first), then by filesize
        audio_formats.sort(key=lambda x: (
            x.get('abr', 0) or 0,
            x.get('filesize', 0) or x.get('filesize_approx', 0) or 0
        ), reverse=True)
        best_audio = audio_formats[0]
        logger.info(f"Selected audio format: {best_audio.get('format_note', 'Unknown')} "
                   f"({best_audio.get('abr', 0)} kbps)")
        return best_audio.get('url')
    
    # Fallback to any format with audio
    for f in formats:
        if f.get('acodec') != 'none' and f.get('url'):
            logger.info(f"Using fallback audio format: {f.get('format_note', 'Unknown')}")
            return f.get('url')
    
    return None

# ------------------ ROUTES ------------------

@app.get("/")
def root():
    return {
        "message": "Enhanced YouTube Music API is RUNNING!",
        "version": "4.0.0",
        "endpoints": {
            "/play/{video_id}": "Get audio URL and metadata",
            "/redirect/{video_id}": "Redirect directly to audio stream",
            "/test/{video_id}": "HTML test page for audio playback",
            "/health": "Health check endpoint"
        },
        "example": "https://your-app.onrender.com/play/dQw4w9WgXcQ"
    }

@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "cache_size": len(audio_cache.cache)
    }

@app.get("/play/{video_id}")
def get_audio_url(video_id: str):
    """Get audio URL with enhanced error handling and fallbacks"""
    try:
        # Validate video ID
        if not video_id or len(video_id) != 11:
            raise HTTPException(status_code=400, detail="Invalid video ID format")
        
        # Check cache first
        cached = audio_cache.get(video_id)
        if cached:
            logger.info(f"Cache hit for {video_id}")
            return JSONResponse(content={**cached, "cached": True})

        logger.info(f"Fetching audio URL for: {video_id}")
        
        # Try primary method with retry logic
        info = get_audio_url_with_retry(video_id)
        
        # If primary fails, try alternative sources
        if not info:
            logger.info("Primary method failed, trying alternative sources...")
            info = get_audio_from_alternative_sources(video_id)
        
        if not info:
            raise HTTPException(
                status_code=404, 
                detail="Video not available. YouTube may be blocking requests from this server."
            )
        
        # Extract the best audio URL
        audio_url = extract_best_audio_url(info)
        
        if not audio_url:
            raise HTTPException(status_code=404, detail="No audio stream found for this video")
        
        # Prepare response
        result = {
            "video_id": video_id,
            "title": info.get('title', 'Unknown Title'),
            "artist": info.get('uploader', 'Unknown Artist'),
            "duration": info.get('duration', 0),
            "audio_url": audio_url,
            "thumbnail": info.get('thumbnail'),
            "webpage_url": info.get('webpage_url', f'https://www.youtube.com/watch?v={video_id}'),
            "success": True,
            "message": "Use the audio_url in an audio player or browser"
        }
        
        # Cache the result
        audio_cache.set(video_id, result)
        logger.info(f"Successfully processed {video_id}: {result['title'][:50]}...")
        
        return JSONResponse(content={**result, "cached": False})
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error for {video_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get audio: {str(e)}"
        )

@app.get("/redirect/{video_id}")
def redirect_to_audio(video_id: str):
    """Redirect directly to audio stream with enhanced error handling"""
    try:
        if not video_id or len(video_id) != 11:
            raise HTTPException(status_code=400, detail="Invalid video ID format")
            
        logger.info(f"Redirecting to audio for: {video_id}")
        
        # Try to get cached result first
        cached = audio_cache.get(video_id)
        if cached and cached.get('audio_url'):
            audio_url = cached['audio_url']
            logger.info(f"Using cached audio URL for redirect: {video_id}")
        else:
            # Fetch fresh data
            info = get_audio_url_with_retry(video_id)
            if not info:
                info = get_audio_from_alternative_sources(video_id)
            
            if not info:
                raise HTTPException(status_code=404, detail="Video not found")
            
            audio_url = extract_best_audio_url(info)
            if not audio_url:
                raise HTTPException(status_code=404, detail="No audio stream found")
        
        # Redirect to the audio URL
        response = RedirectResponse(url=audio_url)
        
        # Add headers that YouTube expects
        response.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        response.headers["Referer"] = "https://www.youtube.com/"
        response.headers["Origin"] = "https://www.youtube.com"
        response.headers["Cache-Control"] = "public, max-age=3600"
        
        logger.info(f"Successfully redirecting {video_id} to audio stream")
        return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Redirect error for {video_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Redirect failed: {str(e)}")

@app.get("/test/{video_id}")
def test_playback(video_id: str):
    """Simple test endpoint that returns HTML to play audio"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Audio Player Test</title>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .player-container {{
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                margin: 20px 0;
            }}
            audio {{
                width: 100%;
                margin: 10px 0;
            }}
            .links {{
                margin: 20px 0;
            }}
            .links a {{
                display: block;
                margin: 10px 0;
                padding: 10px;
                background: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                text-align: center;
            }}
            .links a:hover {{
                background: #0056b3;
            }}
            .status {{
                padding: 10px;
                border-radius: 5px;
                margin: 10px 0;
            }}
            .success {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }}
            .error {{
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }}
        </style>
    </head>
    <body>
        <h1>🎵 YouTube Audio Player Test</h1>
        <div class="player-container">
            <h2>Video ID: <code>{video_id}</code></h2>
            
            <div id="status"></div>
            
            <h3>Audio Player:</h3>
            <audio controls autoplay id="audioPlayer" style="width: 100%;">
                <source src="/redirect/{video_id}" type="audio/mp4">
                Your browser does not support the audio element.
            </audio>
            
            <div class="links">
                <a href="/play/{video_id}" target="_blank">📋 Get Audio URL JSON</a>
                <a href="/redirect/{video_id}" target="_blank">🔗 Direct Audio Link</a>
                <a href="https://www.youtube.com/watch?v={video_id}" target="_blank">📺 Original YouTube Video</a>
            </div>
        </div>

        <script>
            const audioPlayer = document.getElementById('audioPlayer');
            const statusDiv = document.getElementById('status');
            
            audioPlayer.addEventListener('loadstart', function() {{
                statusDiv.innerHTML = '<div class="status">🔄 Loading audio...</div>';
            }});
            
            audioPlayer.addEventListener('canplay', function() {{
                statusDiv.innerHTML = '<div class="status success">✅ Audio loaded successfully! Playing...</div>';
            }});
            
            audioPlayer.addEventListener('error', function(e) {{
                statusDiv.innerHTML = '<div class="status error">❌ Error loading audio. The server may be blocked by YouTube.</div>';
                console.error('Audio error:', e);
            }});
            
            // Test the API endpoint
            fetch('/play/{video_id}')
                .then(response => response.json())
                .then(data => {{
                    console.log('API response:', data);
                }})
                .catch(error => {{
                    console.error('API test failed:', error);
                }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/cache/clear")
def clear_cache():
    """Clear the audio cache (admin endpoint)"""
    previous_size = len(audio_cache.cache)
    audio_cache.cache.clear()
    logger.info(f"Cache cleared. Previous size: {previous_size}")
    return {
        "message": "Cache cleared successfully",
        "previous_size": previous_size,
        "current_size": 0
    }

@app.get("/cache/status")
def cache_status():
    """Get cache status information"""
    return {
        "cache_size": len(audio_cache.cache),
        "max_size": audio_cache.max_size,
        "ttl": audio_cache.ttl,
        "cached_videos": list(audio_cache.cache.keys())
    }

# ------------------ START THE SERVER ------------------
if __name__ == "__main__":
    import uvicorn
    
    print("🎵 Enhanced YouTube Music API Starting...")
    print("🔧 Version 4.0.0 - Cloud Optimized")
    print("📢 Available endpoints:")
    print("   http://localhost:8000/play/dQw4w9WgXcQ")
    print("   http://localhost:8000/redirect/dQw4w9WgXcQ") 
    print("   http://localhost:8000/test/dQw4w9WgXcQ")
    print("   http://localhost:8000/health")
    print("   http://localhost:8000/cache/status")
    
    # Check if cookies file exists
    cookies_file = os.getenv("COOKIES_FILE", "cookies.txt")
    if os.path.exists(cookies_file):
        print(f"✅ Cookies file found: {cookies_file}")
    else:
        print(f"⚠️  No cookies file found at {cookies_file}. Some features may not work.")
        print("   Consider exporting YouTube cookies for better reliability.")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
