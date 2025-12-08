# 🎵 Home MP3 Hub - YT Downloader

A self-hosted, local-network YouTube to MP3 downloader running on your NAS. Anyone in your household can share YouTube links through a beautiful web interface, and the app automatically downloads and organizes the audio files.

## Features

- 🌐 **Web Interface** - Beautiful, responsive UI accessible from any device on your local network
- 📱 **Mobile Friendly** - Works perfectly on iOS and Android
- 🎬 **YouTube Integration** - Paste any YouTube URL and download audio as MP3
- 📁 **Configurable Storage** - Choose where downloaded files are saved
- 🔄 **Real-time Updates** - Watch downloads progress in real-time
- 🎯 **Local Only** - Everything runs on your NAS, no cloud uploads, no tracking
- 🐳 **Docker Ready** - One-command deployment with Docker Compose

## Prerequisites

- NAS with Docker support (Synology, QNAP, Unraid, or any Docker-capable system)
- Docker and Docker Compose installed
- At least 5GB free disk space for downloads
- Network connectivity between devices and NAS

## Deployment

### Using Docker or Podman?

This guide uses **Docker Compose**, but the files also work with **Podman**!

- **Docker**: `docker-compose up -d`
- **Podman**: `podman compose up -d` (built-in, no hyphen)

> Note: Podman 3.0+ includes `podman compose` built-in. Use `podman compose` (with space, no hyphen) - no need to install `podman-compose` separately.

See `PODMAN_SETUP.md` for detailed Podman instructions.

### 1. Prepare Your NAS

Create a directory structure for the application:

```bash
mkdir -p /volume1/docker/youtube-downloader
cd /volume1/docker/youtube-downloader
```

Replace `/volume1` with your actual NAS mount point (e.g., `/mnt/disk1` for Unraid, `/data` for QNAP).

### 2. Download or Clone the Application

If you have git:
```bash
git clone <repository-url> .
```

Or manually create the directory structure and copy all files.

### 3. Configure Storage Path

Edit `docker-compose.yml` and update the downloads volume:

```yaml
volumes:
  - /your/nas/music/path:/downloads  # Change this to your desired location
```

For example:
- **Synology**: `/volume1/music:/downloads`
- **QNAP**: `/share/Music:/downloads`
- **Unraid**: `/mnt/user/media/music:/downloads`

### 4. Build and Start the Containers

**Using Docker:**
```bash
cd /volume1/docker/youtube-downloader
docker-compose build
docker-compose up -d
```

**Using Podman:**
```bash
cd /volume1/docker/youtube-downloader
podman compose build
podman compose up -d
```

> Podman 3.0+ includes `podman compose` built-in (with space, no hyphen). See `PODMAN_SETUP.md` for more details.

### 5. Verify It's Running

**Using Docker:**
```bash
docker-compose ps
```

**Using Podman:**
```bash
podman compose ps
```

You should see both `youtube-downloader-backend` and `youtube-downloader-frontend` as running.

> For Podman, see `PODMAN_SETUP.md` for more verification commands.

### 6. Access the Application

Open your browser and navigate to:
- **Local IP**: `http://<your-nas-ip>`
- **Hostname**: `http://nas.local` (if your NAS supports mDNS)

Example: `http://192.168.1.100`

## Usage

### From the Web Interface

1. Open the app on any device on your network
2. Paste a YouTube URL in the "Add Video" section
3. (Optional) Enter a custom filename
4. Click "Download MP3"
5. Monitor progress in the "Recent Downloads" section
6. Downloaded files appear in the "Downloaded Files" section

### Configurable Options

Click the ⚙️ button to access settings:

- **Download Directory**: Change where MP3s are saved
- **Organization Options**: Auto-organize by date or artist (coming soon)

## API Endpoints

If you want to integrate with Home Assistant or other tools:

```bash
# Health check
GET http://<nas-ip>:8000/health

# Get configuration
GET http://<nas-ip>:8000/config

# Update configuration
POST http://<nas-ip>:8000/config
Body: {"download_path": "/path/to/downloads"}

# Start download
POST http://<nas-ip>:8000/download
Body: {"url": "https://youtube.com/watch?v=...", "custom_name": "My Song"}

# Get all downloads
GET http://<nas-ip>:8000/downloads

# Get specific download status
GET http://<nas-ip>:8000/downloads/{download_id}

# Get downloaded files
GET http://<nas-ip>:8000/files

# Clear download
DELETE http://<nas-ip>:8000/downloads/{download_id}
```

## Home Assistant Integration

You can trigger downloads from Home Assistant automations:

```yaml
# automation.yaml
automation:
  - alias: "Download from YouTube URL"
    trigger:
      platform: time
      at: "10:00:00"
    action:
      - service: rest_command.download_youtube
        data:
          url: "https://youtube.com/watch?v=..."

# configuration.yaml
rest_command:
  download_youtube:
    url: "http://192.168.1.100:8000/download"
    method: POST
    payload: '{"url": "{{ url }}"}'
    content_type: "application/json"
```

## Troubleshooting

### Containers won't start
```bash
docker-compose logs backend
docker-compose logs frontend
```

### Download fails with "Invalid YouTube URL"
- Ensure the URL is a full YouTube link (https://youtube.com/watch?v=...)
- Try a different video

### Can't access from other devices
- Ensure devices are on the same network as the NAS
- Check NAS firewall settings - port 80 should be accessible
- Try accessing via NAS IP address instead of hostname

### Downloads are very slow
- Check your NAS internet connection
- Close other bandwidth-heavy applications
- Try downloading a different video first

### "FFmpeg not found" error
- The Docker image includes FFmpeg. This should not occur.
- If it does, try rebuilding: `docker-compose build --no-cache`

## Managing Downloads Directory

The downloads directory is mounted as a Docker volume. To manage files:

**Via NAS File Manager:**
- Browse to the configured directory path
- Delete old files as needed

**Via Docker:**
```bash
# List files
docker exec youtube-downloader-backend ls -la /downloads

# Delete a file
docker exec youtube-downloader-backend rm /downloads/song.mp3
```

## Updating the Application

```bash
cd /volume1/docker/youtube-downloader
git pull  # or manually update files
docker-compose build --no-cache
docker-compose up -d
```

## Stopping the Application

```bash
docker-compose stop
```

## Removing the Application

```bash
docker-compose down -v  # -v removes volumes
```

## Performance Notes

- **Recommended NAS**: At least 2GB RAM, multi-core processor
- **Concurrent Downloads**: Default is 3, adjustable in config
- **Storage**: Plan ~10MB per song, varies by length and quality

## Security & Privacy

- ✅ All processing happens locally on your NAS
- ✅ No data sent to external servers
- ✅ No user tracking or analytics
- ✅ No account creation required
- ⚠️ YouTube's terms of service don't permit downloading content. This is for personal, educational use only.

## Advanced Configuration

### Custom Domain/Reverse Proxy

To access via a custom domain (e.g., `mp3.local`), set up a reverse proxy:

**Using Nginx Proxy Manager:**
```
Hostname: mp3.local
Scheme: http
Forward Hostname/IP: <nas-ip>
Forward Port: 80
```

### Multiple Storage Paths

Edit `docker-compose.yml` to mount multiple directories:
```yaml
volumes:
  - /volume1/music:/downloads/main
  - /volume2/music:/downloads/backup
```

## Support & Contribution

Found a bug? Have a feature request? Feel free to open an issue or contribute to the project.

## License

This project is provided as-is for personal use.

---

**Made for Home Networks** 🏠
