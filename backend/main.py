from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import yt_dlp
import os
import json
from pathlib import Path
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube MP3 Downloader")

# CORS configuration for local network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load configuration
CONFIG_FILE = Path("/app/config/config.json")
DEFAULT_CONFIG = {
    "download_path": "/downloads",
    "max_concurrent_downloads": 3,
    "organize_by_date": False,
    "organize_by_artist": True
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return DEFAULT_CONFIG

def save_config(config):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

config = load_config()

# Ensure download directory exists
download_path = Path(config["download_path"])
download_path.mkdir(parents=True, exist_ok=True)

# Track ongoing downloads
downloads = {}

class DownloadRequest(BaseModel):
    url: str
    custom_name: Optional[str] = None

class ConfigUpdate(BaseModel):
    download_path: Optional[str] = None
    max_concurrent_downloads: Optional[int] = None
    organize_by_date: Optional[bool] = None
    organize_by_artist: Optional[bool] = None

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/config")
async def get_config():
    return config

@app.post("/config")
async def update_config(update: ConfigUpdate):
    global config
    update_data = update.dict(exclude_unset=True)
    config.update(update_data)
    save_config(config)
    return config

@app.post("/download")
async def download_youtube(request: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Queue a YouTube video for MP3 download
    """
    url = request.url.strip()
    
    # Validate URL
    if not is_valid_youtube_url(url):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    download_id = f"dl_{int(datetime.now().timestamp() * 1000)}"
    downloads[download_id] = {
        "status": "queued",
        "url": url,
        "progress": 0,
        "title": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    
    background_tasks.add_task(perform_download, download_id, url, request.custom_name)
    
    return {
        "download_id": download_id,
        "status": "queued",
        "message": "Download queued successfully"
    }

@app.get("/downloads/{download_id}")
async def get_download_status(download_id: str):
    """
    Get status of a specific download
    """
    if download_id not in downloads:
        raise HTTPException(status_code=404, detail="Download not found")
    
    return downloads[download_id]

@app.get("/downloads")
async def list_downloads():
    """
    List all downloads (recent first)
    """
    sorted_downloads = sorted(
        downloads.items(),
        key=lambda x: x[1]["created_at"],
        reverse=True
    )
    return {item[0]: item[1] for item in sorted_downloads}

@app.get("/files")
async def list_downloaded_files():
    """
    List all downloaded MP3 files
    """
    mp3_files = []
    
    for root, dirs, files in os.walk(download_path):
        for file in files:
            if file.endswith('.mp3'):
                file_path = Path(root) / file
                mp3_files.append({
                    "name": file,
                    "path": str(file_path.relative_to(download_path)),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
    
    return sorted(mp3_files, key=lambda x: x["modified"], reverse=True)

def is_valid_youtube_url(url: str) -> bool:
    """Validate if URL is a YouTube URL"""
    youtube_domains = ["youtube.com", "youtu.be", "www.youtube.com"]
    return any(domain in url for domain in youtube_domains)

def perform_download(download_id: str, url: str, custom_name: Optional[str]):
    """
    Perform the actual download in background
    """
    try:
        downloads[download_id]["status"] = "downloading"
        
        output_path = download_path
        
        # Create output path subdirectory if organizing
        if config.get("organize_by_date"):
            date_folder = datetime.now().strftime("%Y-%m-%d")
            output_path = download_path / date_folder
            output_path.mkdir(exist_ok=True)
        
        # Configure yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(output_path / (custom_name or '%(title)s')),
            'quiet': False,
            'no_warnings': False,
            'progress_hooks': [lambda d: update_progress(download_id, d)],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown')
            
            downloads[download_id].update({
                "status": "completed",
                "title": title,
                "progress": 100,
                "completed_at": datetime.now().isoformat()
            })
            
            logger.info(f"Download completed: {download_id} - {title}")
    
    except Exception as e:
        logger.error(f"Download failed: {download_id} - {str(e)}")
        downloads[download_id].update({
            "status": "error",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })

def update_progress(download_id: str, d):
    """Update progress for a download"""
    if d['status'] == 'downloading':
        if d['total_bytes'] > 0:
            progress = int(d['downloaded_bytes'] / d['total_bytes'] * 100)
            downloads[download_id]["progress"] = progress
    elif d['status'] == 'finished':
        downloads[download_id]["progress"] = 100

@app.delete("/downloads/{download_id}")
async def clear_download(download_id: str):
    """Clear a download from the queue"""
    if download_id in downloads:
        del downloads[download_id]
        return {"message": "Download cleared"}
    raise HTTPException(status_code=404, detail="Download not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)