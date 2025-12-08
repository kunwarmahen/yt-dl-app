from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import yt_dlp
import os
import json
from pathlib import Path
from datetime import datetime
import logging
import threading

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
download_path_str = os.getenv('DOWNLOAD_PATH') or config.get("download_path", "/downloads")

logger.info(f"Using download path: {download_path_str}")

download_path = Path(download_path_str)

try:
    download_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Download directory ready: {download_path.absolute()}")
except PermissionError as e:
    logger.error(f"Permission denied creating download directory at {download_path_str}")
    logger.error(f"Error: {str(e)}")
    logger.error("Make sure:")
    logger.error("  - Directory exists and is writable")
    logger.error("  - DOWNLOAD_PATH environment variable is set correctly")
    logger.error("  - Container volume is mounted correctly")
    raise
except Exception as e:
    logger.error(f"Error creating download directory: {str(e)}")
    raise

# Track ongoing downloads
downloads = {}
# Track downloads to cancel
cancel_downloads = set()
downloads_lock = threading.Lock()

class DownloadRequest(BaseModel):
    url: str
    custom_name: Optional[str] = None
    download_list: bool = False

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
async def download_youtube(request: DownloadRequest, background_tasks: BackgroundTasks, req: Request):
    """
    Queue a YouTube video for MP3 download
    """
    url = request.url.strip()
    
    # Get real client IP from headers (try X-Forwarded-For first for proxy/container environments)
    client_ip = None
    
    # Try X-Forwarded-For header first (for proxies, load balancers)
    if "x-forwarded-for" in req.headers:
        client_ip = req.headers["x-forwarded-for"].split(",")[0].strip()
    # Try X-Real-IP header (common in reverse proxies)
    elif "x-real-ip" in req.headers:
        client_ip = req.headers["x-real-ip"]
    # Fall back to direct connection
    elif req.client:
        client_ip = req.client.host
    
    # Only show IP if it's not localhost/container IP
    if client_ip and (client_ip.startswith("127.") or client_ip.startswith("172.") or 
                      client_ip.startswith("192.168.") or client_ip == "::1"):
        client_ip = None
    
    # Get MAC address from ARP (best effort, may not work in all environments)
    mac_address = None
    if client_ip:
        try:
            import subprocess
            import platform
            
            if platform.system() == "Linux":
                # Try to get MAC from ARP
                result = subprocess.run(
                    ["arp", "-n", client_ip],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if client_ip in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                mac_address = parts[2]
                                break
        except Exception as e:
            logger.debug(f"Could not get MAC address: {str(e)}")
    
    logger.info(f"Download request received. URL: {url}, Download list: {request.download_list}, IP: {client_ip}, MAC: {mac_address}")
    
    # Validate URL
    if not is_valid_youtube_url(url):
        logger.error(f"Invalid YouTube URL: {url}")
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    download_id = f"dl_{int(datetime.now().timestamp() * 1000)}"
    downloads[download_id] = {
        "status": "queued",
        "url": url,
        "progress": 0,
        "title": None,
        "error": None,
        "created_at": datetime.now().timestamp(),
        "client_ip": client_ip,
        "mac_address": mac_address
    }
    
    background_tasks.add_task(perform_download, download_id, url, request.custom_name, request.download_list)
    
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
                stat_info = file_path.stat()
                file_size = stat_info.st_size
                
                # Send timestamp as Unix timestamp, let frontend convert to local time
                mtime_timestamp = stat_info.st_mtime
                
                file_obj = {
                    "name": file,
                    "path": str(file_path.relative_to(download_path)),
                    "size": int(file_size),
                    "modified": mtime_timestamp
                }
                logger.info(f"File: {file}, Size: {file_size}, Modified: {mtime_timestamp}")
                mp3_files.append(file_obj)
    
    logger.info(f"Total files found: {len(mp3_files)}")
    return sorted(mp3_files, key=lambda x: x["modified"], reverse=True)

def is_valid_youtube_url(url: str) -> bool:
    """Validate if URL is a YouTube URL"""
    url = url.strip().lower()  # Strip whitespace and convert to lowercase
    youtube_domains = ["youtube.com", "youtu.be"]
    return any(domain in url for domain in youtube_domains)

def perform_download(download_id: str, url: str, custom_name: Optional[str], download_list: bool = False):
    """
    Perform the actual download in background
    """
    try:
        with downloads_lock:
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
        
        # If not downloading list, only download first item
        if not download_list:
            ydl_opts['playlist_items'] = '1'
        
        def check_cancel(d):
            """Check if download should be cancelled"""
            with downloads_lock:
                if download_id in cancel_downloads:
                    return True
            return False
        
        # Add cancellation hook
        ydl_opts['progress_hooks'].append(lambda d: (
            check_cancel(d) and (_ for _ in ()).throw(Exception("Download cancelled by user"))
        ))
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown')
            
            with downloads_lock:
                downloads[download_id].update({
                    "status": "completed",
                    "title": title,
                    "progress": 100,
                    "completed_at": datetime.now().timestamp()
                })
            
            logger.info(f"Download completed: {download_id} - {title}")
    
    except Exception as e:
        error_msg = str(e)
        is_cancelled = "cancelled" in error_msg.lower()
        
        logger.error(f"Download failed: {download_id} - {error_msg}")
        with downloads_lock:
            downloads[download_id].update({
                "status": "cancelled" if is_cancelled else "error",
                "error": error_msg,
                "completed_at": datetime.now().timestamp()
            })
            # Remove from cancel set if it was cancelled
            cancel_downloads.discard(download_id)
    
    finally:
        # Clean up cancel flag
        with downloads_lock:
            cancel_downloads.discard(download_id)

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

@app.post("/downloads/{download_id}/cancel")
async def cancel_download(download_id: str):
    """Cancel an ongoing download"""
    with downloads_lock:
        if download_id not in downloads:
            raise HTTPException(status_code=404, detail="Download not found")
        
        download = downloads[download_id]
        if download["status"] not in ["downloading", "queued"]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed or error download")
        
        # Mark for cancellation
        cancel_downloads.add(download_id)
        downloads[download_id]["status"] = "cancelling"
    
    logger.info(f"Cancel requested for download: {download_id}")
    return {"message": "Cancellation requested", "download_id": download_id}

@app.delete("/files/{filename}")
async def delete_file(filename: str):
    """Delete an MP3 file from the filesystem"""
    try:
        from urllib.parse import unquote
        filename = unquote(filename)
        
        # Sanitize filename to prevent directory traversal
        filename = filename.strip()
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        file_path = download_path / filename
        
        # Check if file exists
        if not file_path.exists():
            logger.warning(f"Delete request for non-existent file: {filename}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if file is actually an MP3
        if not filename.lower().endswith('.mp3'):
            raise HTTPException(status_code=400, detail="Only MP3 files can be deleted")
        
        # Delete the file
        file_path.unlink()
        logger.info(f"Deleted file: {filename}")
        
        return {"message": f"File deleted: {filename}"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting file")

@app.get("/play/{filename}")
async def play_file(filename: str):
    """Stream an MP3 file for playback"""
    try:
        # URL decode the filename (handles spaces, special chars)
        from urllib.parse import unquote
        filename = unquote(filename)
        
        # Sanitize filename to prevent directory traversal
        filename = filename.strip()
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        file_path = download_path / filename
        
        # Check if file exists
        if not file_path.exists():
            logger.warning(f"Play request for non-existent file: {filename}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if file is actually an MP3
        if not filename.lower().endswith('.mp3'):
            raise HTTPException(status_code=400, detail="Only MP3 files can be played")
        
        logger.info(f"Streaming file: {filename}")
        
        # Return file for streaming with proper headers
        from fastapi.responses import FileResponse
        from urllib.parse import quote
        
        # RFC 5987 encoding for filename with special characters
        # Properly encode filename for use in header
        encoded_filename = quote(filename, safe='')
        
        return FileResponse(
            file_path,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming file {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error streaming file")

@app.get("/download-file/{filename}")
async def download_file(filename: str):
    """Download an MP3 file"""
    try:
        # URL decode the filename (handles spaces, special chars)
        from urllib.parse import unquote
        filename = unquote(filename)
        
        # Sanitize filename to prevent directory traversal
        filename = filename.strip()
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        file_path = download_path / filename
        
        # Check if file exists
        if not file_path.exists():
            logger.warning(f"Download request for non-existent file: {filename}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if file is actually an MP3
        if not filename.lower().endswith('.mp3'):
            raise HTTPException(status_code=400, detail="Only MP3 files can be downloaded")
        
        logger.info(f"Downloading file: {filename}")
        
        # Return file for download with proper headers
        from fastapi.responses import FileResponse
        from urllib.parse import quote
        
        # RFC 5987 encoding for filename with special characters
        # Properly encode filename for use in header
        encoded_filename = quote(filename, safe='')
        
        return FileResponse(
            file_path,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error downloading file")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)