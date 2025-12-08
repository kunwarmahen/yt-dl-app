# Podman to Docker Migration - Complete Step-by-Step Guide

## Overview

This guide walks through migrating from Podman (local development) to Docker (NAS deployment) using your actual tested commands.

---

## Prerequisites

- Local machine with Podman and images built
- NAS with Docker installed
- SSH access to NAS
- ~1-2GB for tar files during transfer
- Network connection between machines

---

## Step 1: Build Images on Local Machine (Podman)

### 1.1 Build Backend Image

```bash
cd ~/youtube-downloader

docker build -f backend/Dockerfile \
  -t youtube-downloader-backend:latest \
  ./backend
```

### 1.2 Build Frontend Image

```bash
docker build -f frontend/Dockerfile \
  --build-arg REACT_APP_API_URL=/api \
  -t youtube-downloader-frontend:latest \
  ./frontend
```

### 1.3 Verify Images Built

```bash
docker images | grep youtube-downloader

# Should show:
# youtube-downloader-backend   latest
# youtube-downloader-frontend  latest
```

---

## Step 2: Export Images as TAR Files

### 2.1 Export Backend Image

```bash
docker save -o youtube-downloader-backend.tar youtube-downloader-backend:latest
```

### 2.2 Export Frontend Image

```bash
docker save -o youtube-downloader-frontend.tar youtube-downloader-frontend:latest
```

### 2.3 Verify TAR Files

```bash
ls -lh youtube-downloader-*.tar

# Should show files around 300-500MB each
```

---

## Step 3: Transfer TAR Files to NAS

### 3.1 Using SCP (Recommended)

```bash
# Transfer both files at once
scp youtube-downloader-*.tar admin@192.168.1.44:/home/admin/
```

### 3.2 Using SSH Copy (Alternative)

```bash
scp youtube-downloader-backend.tar admin@192.168.1.44:/home/admin/
scp youtube-downloader-frontend.tar admin@192.168.1.44:/home/admin/
```

### 3.3 Verify Transfer (On NAS)

```bash
ssh admin@192.168.1.44

ls -lh ~/youtube-downloader-*.tar

# Should show both files transferred
```

---

## Step 4: Stop and Remove Old Containers (If Upgrading)

### 4.1 Connect to NAS

```bash
ssh admin@192.168.1.44
```

### 4.2 Stop Running Containers

```bash
# Stop backend
sudo docker stop youtube-backend

# Stop frontend
sudo docker stop youtube-frontend
```

### 4.3 Remove Containers

```bash
# Remove backend
sudo docker rm youtube-backend

# Remove frontend
sudo docker rm youtube-frontend
```

### 4.4 Remove Old Images (Optional)

```bash
# Only if you want to clean up old images
sudo docker rmi youtube-downloader-backend:latest
sudo docker rmi youtube-downloader-frontend:latest
```

---

## Step 5: Load Docker Images from TAR Files

### 5.1 Load Backend Image

```bash
sudo docker load -i ~/youtube-downloader-backend.tar
```

### 5.2 Load Frontend Image

```bash
sudo docker load -i ~/youtube-downloader-frontend.tar
```

### 5.3 Verify Images Loaded

```bash
sudo docker images | grep youtube-downloader

# Should show both images
```

---

## Step 6: Create Docker Network

### 6.1 Create Network

```bash
sudo docker network create youtube-network
```

### 6.2 Verify Network Created

```bash
sudo docker network ls | grep youtube

# Should show: youtube-network
```

---

## Step 7: Deploy Backend Container

### 7.1 Start Backend

**Option A: With Custom Download Path**

```bash
sudo docker run -d \
  --name youtube-backend \
  --network youtube-network \
  -p 8000:8000 \
  -v /volume1/Web/youtube/downloader:/downloads \
  -e DOWNLOAD_PATH=/downloads \
  --restart unless-stopped \
  youtube-downloader-backend:latest
```

**Option B: With Default Path**

```bash
sudo docker run -d \
  --name youtube-backend \
  --network youtube-network \
  -p 8000:8000 \
  -v /mnt/downloads:/downloads \
  --restart unless-stopped \
  youtube-downloader-backend:latest
```

### 7.2 Verify Backend Running

```bash
sudo docker ps | grep youtube-backend

# Should show container running
```

### 7.3 Check Backend Logs

```bash
sudo docker logs youtube-backend

# Should show: "Application startup complete"
```

### 7.4 Test Backend Health

```bash
curl http://localhost:8000/health

# Should return: {"status":"healthy"}
```

---

## Step 8: Deploy Frontend Container

### 8.1 Start Frontend

```bash
sudo docker run -d \
  --name youtube-frontend \
  --network youtube-network \
  -p 8080:80 \
  --restart unless-stopped \
  youtube-downloader-frontend:latest
```

### 8.2 Verify Frontend Running

```bash
sudo docker ps | grep youtube-frontend

# Should show container running
```

### 8.3 Check Frontend Logs

```bash
sudo docker logs youtube-frontend

# Should show Nginx startup messages
```

### 8.4 Test Frontend Health

```bash
curl http://localhost:8080/health

# Should return: healthy
```

---

## Step 9: Verify Communication Between Containers

### 9.1 Test from Frontend to Backend

```bash
sudo docker exec youtube-frontend curl -i http://youtube-backend:8000/config

# Should return config JSON
```

### 9.2 Test API Endpoint

```bash
curl http://localhost:8080/api/config

# Should return: {"download_path":"/downloads","max_concurrent_downloads":3, ...}
```

---

## Step 10: Access the Application

### 10.1 From NAS Machine

```
http://localhost:8080
```

### 10.2 From Another Device on Network

```
http://192.168.1.44:8080
```

### 10.3 API Endpoints

```
Backend directly: http://192.168.1.44:8000
API through proxy: http://192.168.1.44:8080/api/
```

---

## Complete One-Liner (For Experienced Users)

If you want to deploy everything at once after loading images:

```bash
# Create network
sudo docker network create youtube-network

# Start backend and frontend
sudo docker run -d \
  --name youtube-backend \
  --network youtube-network \
  -p 8000:8000 \
  -v /volume1/Web/youtube/downloader:/downloads \
  -e DOWNLOAD_PATH=/downloads \
  --restart unless-stopped \
  youtube-downloader-backend:latest && \
sudo docker run -d \
  --name youtube-frontend \
  --network youtube-network \
  -p 8080:80 \
  --restart unless-stopped \
  youtube-downloader-frontend:latest && \
echo "✅ Deployment complete! Access at http://localhost:8080"
```

---

## Port Mapping Reference

Your setup uses non-standard ports:

| Service  | Internal Port | External Port | URL                      |
| -------- | ------------- | ------------- | ------------------------ |
| Backend  | 8000          | 8000          | http://192.168.1.44:8000 |
| Frontend | 80            | 8080          | http://192.168.1.44:8080 |

**Why 8080?** Port 80 might be used by other services, so 8080 is used instead.

---

## Download Path Reference

Your setup uses custom download path:

```
/volume1/Web/youtube/downloader:/downloads
```

This means:

- Files stored on NAS at: `/volume1/Web/youtube/downloader/`
- Inside container mapped to: `/downloads`
- Backend knows about: `/downloads`

---

## Docker Run Parameters Explained

### Backend Container

```bash
sudo docker run -d \                          # Run detached (background)
  --name youtube-backend \                    # Container name
  --network youtube-network \                 # Join custom network
  -p 8000:8000 \                              # Port mapping: host:container
  -v /volume1/Web/youtube/downloader:/downloads \  # Volume mount: host:container
  -e DOWNLOAD_PATH=/downloads \               # Environment variable
  --restart unless-stopped \                  # Auto-restart on failure
  youtube-downloader-backend:latest           # Image name:tag
```

### Frontend Container

```bash
sudo docker run -d \                          # Run detached
  --name youtube-frontend \                   # Container name
  --network youtube-network \                 # Join custom network
  -p 8080:80 \                                # Port mapping: host:container
  --restart unless-stopped \                  # Auto-restart on failure
  youtube-downloader-frontend:latest          # Image name:tag
```

---

## Troubleshooting

### Containers Won't Start

**Check logs:**

```bash
sudo docker logs youtube-backend
sudo docker logs youtube-frontend
```

**Common issues:**

- Port already in use → Change port mapping
- Download directory doesn't exist → Create it: `mkdir -p /volume1/Web/youtube/downloader`
- Permission denied → Use `sudo` or add user to docker group

### Can't Access Frontend

**Check if running:**

```bash
sudo docker ps
```

**Check port:**

```bash
sudo netstat -tlnp | grep 8080
```

**Test directly:**

```bash
curl http://localhost:8080
```

### Frontend Can't Connect to Backend

**Check network:**

```bash
sudo docker network inspect youtube-network
```

**Check container is on network:**

```bash
sudo docker inspect youtube-backend | grep NetworkSettings
```

**Test connection:**

```bash
sudo docker exec youtube-frontend curl -i http://youtube-backend:8000/health
```

### Download Directory Issues

**Verify directory exists:**

```bash
ls -la /volume1/Web/youtube/downloader/
```

**Fix permissions:**

```bash
sudo chmod 755 /volume1/Web/youtube/downloader/
```

**Check volume mounted correctly:**

```bash
sudo docker exec youtube-backend ls -la /downloads/
```

---

## Useful Commands

### View Running Containers

```bash
sudo docker ps

# Show all (including stopped)
sudo docker ps -a
```

### View Container Logs

```bash
# Real-time logs
sudo docker logs -f youtube-backend

# Last 50 lines
sudo docker logs --tail=50 youtube-backend

# With timestamps
sudo docker logs -t youtube-backend
```

### Stop Containers

```bash
sudo docker stop youtube-backend
sudo docker stop youtube-frontend
```

### Restart Containers

```bash
sudo docker restart youtube-backend
sudo docker restart youtube-frontend
```

### Remove Containers

```bash
sudo docker rm youtube-backend
sudo docker rm youtube-frontend
```

### Check Container Health

```bash
sudo docker inspect youtube-backend --format='{{.State.Health}}'
```

### Execute Command in Container

```bash
sudo docker exec youtube-backend curl http://localhost:8000/health
```

---

## Update Procedure

When you have new images to deploy:

### 1. Build and Export

```bash
cd ~/youtube-downloader

# Rebuild images
docker build -f backend/Dockerfile -t youtube-downloader-backend:latest ./backend
docker build -f frontend/Dockerfile --build-arg REACT_APP_API_URL=/api -t youtube-downloader-frontend:latest ./frontend

# Export
docker save -o youtube-downloader-backend.tar youtube-downloader-backend:latest
docker save -o youtube-downloader-frontend.tar youtube-downloader-frontend:latest
```

### 2. Transfer and Deploy

```bash
# Transfer
scp youtube-downloader-*.tar admin@192.168.1.44:/home/admin/

# On NAS
ssh admin@192.168.1.44

# Stop old containers
sudo docker stop youtube-backend youtube-frontend
sudo docker rm youtube-backend youtube-frontend

# Remove old images (optional)
sudo docker rmi youtube-downloader-backend:latest
sudo docker rmi youtube-downloader-frontend:latest

# Load new images
sudo docker load -i ~/youtube-downloader-backend.tar
sudo docker load -i ~/youtube-downloader-frontend.tar

# Start new containers
sudo docker run -d \
  --name youtube-backend \
  --network youtube-network \
  -p 8000:8000 \
  -v /volume1/Web/youtube/downloader:/downloads \
  -e DOWNLOAD_PATH=/downloads \
  --restart unless-stopped \
  youtube-downloader-backend:latest

sudo docker run -d \
  --name youtube-frontend \
  --network youtube-network \
  -p 8080:80 \
  --restart unless-stopped \
  youtube-downloader-frontend:latest

# Verify
sudo docker ps
```

---

## Performance Optimization

### Limit Container Resources

```bash
sudo docker run -d \
  --name youtube-backend \
  --network youtube-network \
  -p 8000:8000 \
  -v /volume1/Web/youtube/downloader:/downloads \
  -e DOWNLOAD_PATH=/downloads \
  --memory=512m \
  --cpus=1.5 \
  --restart unless-stopped \
  youtube-downloader-backend:latest
```

### Monitor Container Resources

```bash
# Real-time stats
sudo docker stats

# Specific container
sudo docker stats youtube-backend
```

---

## Backup and Recovery

### Backup Downloaded Files

```bash
# Backup to NAS location
tar -czf /backup/youtube-downloads-backup.tar.gz \
  /volume1/Web/youtube/downloader/
```

### Export Containers

```bash
# Export running container as new image
sudo docker commit youtube-backend youtube-downloader-backend-backup:$(date +%Y%m%d)
```

---

## Network Diagram

```
┌──────────────────────────────────────────────┐
│              Your Local Network              │
├──────────────────────────────────────────────┤
│                                              │
│  Your Device (Phone/PC)                      │
│  │                                           │
│  └──→ http://192.168.1.44:8080 ←────┐       │
│                                       │       │
│  ┌─────────────────────────────────┐ │       │
│  │         NAS/Server              │ │       │
│  │  ┌─────────────────────────┐   │ │       │
│  │  │  Docker Networks        │   │ │       │
│  │  │ ┌─────────┐  ┌────────┐ │   │ │       │
│  │  │ │Frontend │→ │Backend │ │   │ │       │
│  │  │ │  :8080  │  │ :8000  │ │   │ │       │
│  │  │ └─────────┘  └────────┘ │   │ │       │
│  │  │       ↓                  │   │ │       │
│  │  │  /volume1/Web/youtube/   │   │ │       │
│  │  │  downloader/             │   │ │       │
│  │  │  (downloaded MP3 files)  │   │ │       │
│  │  └─────────────────────────┘   │ │       │
│  │                                 │ │       │
│  └─────────────────────────────────┘ │       │
│                                       │       │
│       External Port: 8080 ←──────────┘       │
│                                              │
└──────────────────────────────────────────────┘
```

---

## Final Checklist

- [ ] Images built on local machine
- [ ] TAR files exported
- [ ] TAR files transferred to NAS
- [ ] Old containers stopped (if upgrading)
- [ ] Docker network created
- [ ] Backend container running
- [ ] Frontend container running
- [ ] Backend health check passes
- [ ] Frontend health check passes
- [ ] Containers communicate correctly
- [ ] Web interface accessible
- [ ] Download directory created
- [ ] Files can be downloaded
- [ ] Files can be played
- [ ] Auto-restart working

---

## Summary

**This is your complete deployment workflow:**

1. Build images locally → Export as TAR files
2. Transfer TAR files to NAS
3. Create Docker network
4. Load images from TAR
5. Start containers with correct port mappings
6. Access at http://192.168.1.44:8080

**Your exact port setup:**

- NAS internal: port 80 (nginx)
- NAS external: port 8080 (exposed to network)
- Backend: port 8000

**Your exact download path:**

- Host: `/volume1/Web/youtube/downloader/`
- Container: `/downloads`

Everything tested and working! 🚀
