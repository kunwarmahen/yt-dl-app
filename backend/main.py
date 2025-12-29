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
    folder_name: Optional[str] = None

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
    
    background_tasks.add_task(perform_download, download_id, url, request.custom_name, request.download_list, request.folder_name)

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
async def list_downloaded_files(path: str = ""):
    """
    List downloaded MP3 files and folders in a given directory
    Returns items list and metadata (total_files count for root path)
    """
    # Sanitize path to prevent directory traversal
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    # Build current directory path
    current_path = download_path / path if path else download_path

    # Check if directory exists
    if not current_path.exists() or not current_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    items = []

    # List immediate children only (no recursive walk)
    try:
        for item in current_path.iterdir():
            relative_path = str(item.relative_to(download_path))
            stat_info = item.stat()
            mtime_timestamp = stat_info.st_mtime

            if item.is_dir():
                # Count MP3 files in folder
                mp3_count = sum(1 for f in item.rglob('*.mp3'))
                items.append({
                    "name": item.name,
                    "path": relative_path,
                    "type": "folder",
                    "size": 0,
                    "modified": mtime_timestamp,
                    "file_count": mp3_count
                })
            elif item.is_file() and item.suffix.lower() == '.mp3':
                items.append({
                    "name": item.name,
                    "path": relative_path,
                    "type": "file",
                    "size": int(stat_info.st_size),
                    "modified": mtime_timestamp
                })

    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Sort: folders first, then by modified time
    items.sort(key=lambda x: (x["type"] == "file", -x["modified"]))

    # For root path queries, include total file count across all folders
    # This is needed for HACS integration and dashboard stats
    if not path:
        total_files = sum(1 for _ in download_path.rglob('*.mp3'))
        return {
            "items": items,
            "total_files": total_files,
            "current_path": path
        }

    # For subfolder queries, return just the items (backwards compatible)
    return items

def is_valid_youtube_url(url: str) -> bool:
    """Validate if URL is a YouTube URL"""
    url = url.strip().lower()  # Strip whitespace and convert to lowercase
    youtube_domains = ["youtube.com", "youtu.be"]
    return any(domain in url for domain in youtube_domains)

def sanitize_folder_name(name: str) -> str:
    """Sanitize folder name by removing invalid characters"""
    # Remove or replace invalid characters for folder names
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    # Remove leading/trailing dots and spaces
    name = name.strip('. ')
    # Limit length
    return name[:100] if len(name) > 100 else name

def get_unique_folder_name(base_path: Path, folder_name: str) -> str:
    """Get unique folder name by appending (2), (3), etc if folder exists"""
    folder_path = base_path / folder_name
    if not folder_path.exists():
        return folder_name

    counter = 2
    while True:
        new_name = f"{folder_name} ({counter})"
        new_path = base_path / new_name
        if not new_path.exists():
            return new_name
        counter += 1

def perform_download(download_id: str, url: str, custom_name: Optional[str], download_list: bool = False, folder_name: Optional[str] = None):
    """
    Perform the actual download in background
    """
    failed_videos = []
    successful_count = 0

    try:
        with downloads_lock:
            downloads[download_id]["status"] = "downloading"

        output_path = download_path

        # For playlists, create a folder (overrides organize_by_date)
        if download_list:
            # First extract info to get playlist title
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(url, download=False)

                # Use custom folder name if provided, otherwise use playlist title
                if folder_name:
                    playlist_title = folder_name
                else:
                    playlist_title = info.get('title', 'Playlist')

                # Sanitize and create folder name with date
                sanitized_title = sanitize_folder_name(playlist_title)
                date_str = datetime.now().strftime("%Y-%m-%d")
                base_folder_name = f"{sanitized_title} [{date_str}]"

                # Get unique folder name to handle duplicates
                unique_folder_name = get_unique_folder_name(download_path, base_folder_name)
                output_path = download_path / unique_folder_name
                output_path.mkdir(exist_ok=True)

                logger.info(f"Created playlist folder: {unique_folder_name}")

        # For single videos, use organize_by_date if enabled
        elif config.get("organize_by_date"):
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

        # For playlists, continue on errors (skip unavailable videos)
        if download_list:
            ydl_opts['ignoreerrors'] = True
            ydl_opts['quiet'] = True

            # Custom logger to track failed videos
            class PlaylistLogger:
                def __init__(self):
                    self.failed = []

                def debug(self, msg):
                    # Capture unavailable video messages
                    if 'Video unavailable' in msg or 'has been terminated' in msg or 'is not available' in msg:
                        logger.warning(f"Skipping unavailable video: {msg}")

                def warning(self, msg):
                    if 'unavailable' in msg.lower() or 'terminated' in msg.lower():
                        logger.warning(f"Playlist warning: {msg}")
                        self.failed.append(msg)

                def error(self, msg):
                    if 'unavailable' in msg.lower() or 'terminated' in msg.lower():
                        logger.warning(f"Skipping video with error: {msg}")
                        self.failed.append(msg)

            playlist_logger = PlaylistLogger()
            ydl_opts['logger'] = playlist_logger
        else:
            # For single videos, only download first item
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

            if download_list:
                # For playlists, count successful downloads
                title = info.get('title', 'Playlist')
                entries = info.get('entries', [])
                total_videos = len([e for e in entries if e is not None])
                successful_count = len([e for e in entries if e is not None and not e.get('_type') == 'url'])
                failed_count = len(playlist_logger.failed) if hasattr(ydl_opts.get('logger'), 'failed') else 0

                logger.info(f"Playlist download completed: {successful_count} successful, {failed_count} skipped")

                status_msg = f"Downloaded {successful_count} videos"
                if failed_count > 0:
                    status_msg += f" ({failed_count} unavailable videos skipped)"

                with downloads_lock:
                    downloads[download_id].update({
                        "status": "completed",
                        "title": title,
                        "progress": 100,
                        "completed_at": datetime.now().timestamp(),
                        "message": status_msg
                    })
            else:
                # For single videos
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

@app.delete("/files/{file_path:path}")
async def delete_file(file_path: str):
    """Delete an MP3 file from the filesystem"""
    try:
        from urllib.parse import unquote
        file_path = unquote(file_path)

        # Sanitize path to prevent directory traversal
        file_path = file_path.strip()
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")

        full_path = download_path / file_path

        # Check if file exists
        if not full_path.exists():
            logger.warning(f"Delete request for non-existent file: {file_path}")
            raise HTTPException(status_code=404, detail="File not found")

        # Check if it's a file and is an MP3
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        if not file_path.lower().endswith('.mp3'):
            raise HTTPException(status_code=400, detail="Only MP3 files can be deleted")

        # Delete the file
        full_path.unlink()
        logger.info(f"Deleted file: {file_path}")

        return {"message": f"File deleted: {file_path}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting file")

@app.get("/play/{file_path:path}")
async def play_file(file_path: str):
    """Stream an MP3 file for playback"""
    try:
        # URL decode the file path (handles spaces, special chars)
        from urllib.parse import unquote
        file_path = unquote(file_path)

        # Sanitize path to prevent directory traversal
        file_path = file_path.strip()
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")

        full_path = download_path / file_path

        # Check if file exists
        if not full_path.exists():
            logger.warning(f"Play request for non-existent file: {file_path}")
            raise HTTPException(status_code=404, detail="File not found")

        # Check if file is actually an MP3
        if not file_path.lower().endswith('.mp3'):
            raise HTTPException(status_code=400, detail="Only MP3 files can be played")

        logger.info(f"Streaming file: {file_path}")

        # Return file for streaming with proper headers
        from fastapi.responses import FileResponse
        from urllib.parse import quote

        # Get just the filename for the header
        filename = Path(file_path).name
        encoded_filename = quote(filename, safe='')

        return FileResponse(
            full_path,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming file {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error streaming file")

@app.get("/download-file/{file_path:path}")
async def download_file(file_path: str):
    """Download an MP3 file"""
    try:
        # URL decode the file path (handles spaces, special chars)
        from urllib.parse import unquote
        file_path = unquote(file_path)

        # Sanitize path to prevent directory traversal
        file_path = file_path.strip()
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")

        full_path = download_path / file_path

        # Check if file exists
        if not full_path.exists():
            logger.warning(f"Download request for non-existent file: {file_path}")
            raise HTTPException(status_code=404, detail="File not found")

        # Check if file is actually an MP3
        if not file_path.lower().endswith('.mp3'):
            raise HTTPException(status_code=400, detail="Only MP3 files can be downloaded")

        logger.info(f"Downloading file: {file_path}")

        # Return file for download with proper headers
        from fastapi.responses import FileResponse
        from urllib.parse import quote

        # Get just the filename for the header
        filename = Path(file_path).name
        encoded_filename = quote(filename, safe='')

        return FileResponse(
            full_path,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error downloading file")

class RenameRequest(BaseModel):
    old_name: str
    new_name: str

@app.post("/folders/rename")
async def rename_folder(request: RenameRequest):
    """Rename a folder"""
    try:
        # Sanitize paths
        if ".." in request.old_name or ".." in request.new_name:
            raise HTTPException(status_code=400, detail="Invalid folder name")
        if "/" in request.old_name or "\\" in request.old_name:
            raise HTTPException(status_code=400, detail="Invalid old folder name")

        old_path = download_path / request.old_name

        # Sanitize new name
        new_name_sanitized = sanitize_folder_name(request.new_name)
        new_path = download_path / new_name_sanitized

        # Check if old folder exists
        if not old_path.exists() or not old_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")

        # Check if new name already exists
        if new_path.exists():
            raise HTTPException(status_code=400, detail="A folder with that name already exists")

        # Rename the folder
        old_path.rename(new_path)
        logger.info(f"Renamed folder from {request.old_name} to {new_name_sanitized}")

        return {"message": "Folder renamed successfully", "new_name": new_name_sanitized}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming folder: {str(e)}")
        raise HTTPException(status_code=500, detail="Error renaming folder")

@app.delete("/folders/{folder_path:path}")
async def delete_folder(folder_path: str):
    """Delete a folder and all its contents"""
    try:
        from urllib.parse import unquote
        import shutil

        folder_path = unquote(folder_path)

        # Sanitize path to prevent directory traversal
        folder_path = folder_path.strip()
        if ".." in folder_path or folder_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid folder path")

        full_path = download_path / folder_path

        # Check if folder exists
        if not full_path.exists():
            logger.warning(f"Delete request for non-existent folder: {folder_path}")
            raise HTTPException(status_code=404, detail="Folder not found")

        # Check if it's a directory
        if not full_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a folder")

        # Delete the folder and all contents
        shutil.rmtree(full_path)
        logger.info(f"Deleted folder: {folder_path}")

        return {"message": f"Folder deleted: {folder_path}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder {folder_path}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting folder")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)