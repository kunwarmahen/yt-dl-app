#!/bin/bash

# YouTube MP3 Downloader - Quick Start Script

set -e

echo "🎵 YouTube MP3 Downloader - Setup"
echo "=================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✅ Docker and Docker Compose found"
echo ""

# Get the current directory
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "📁 Application directory: $APP_DIR"
echo ""

# Check if docker-compose.yml.template exists
if [ ! -f "$APP_DIR/docker-compose.yml.template" ]; then
    echo "❌ docker-compose.yml.template not found in $APP_DIR"
    exit 1
fi

# Prompt for download path
echo "📋 Configuration"
echo "================"
echo ""
echo "Where should downloaded MP3 files be saved?"
echo "Examples:"
echo "  - /mnt/downloads (generic)"
echo "  - /volume1/music (Synology)"
echo "  - /share/Music (QNAP)"
echo "  - /mnt/user/media/music (Unraid)"
echo ""
read -p "Enter download path: " DOWNLOAD_PATH

if [ -z "$DOWNLOAD_PATH" ]; then
    DOWNLOAD_PATH="/downloads"
    echo "Using default: $DOWNLOAD_PATH"
fi

# Create download directory if it doesn't exist (might not work on all systems)
echo "📁 Creating download directory..."
mkdir -p "$DOWNLOAD_PATH" 2>/dev/null || echo "⚠️  Could not create directory. Please ensure it exists and is writable."

# Generate docker-compose.yml from template
echo "⚙️  Generating docker-compose.yml from template..."
cp "$APP_DIR/docker-compose.yml.template" "$APP_DIR/docker-compose.yml"

# Update docker-compose.yml with the custom path
echo "⚙️  Updating configuration..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s|/mnt/downloads|$DOWNLOAD_PATH|g" "$APP_DIR/docker-compose.yml"
else
    # Linux
    sed -i "s|/mnt/downloads|$DOWNLOAD_PATH|g" "$APP_DIR/docker-compose.yml"
fi

echo ""
echo "🔨 Building Docker images..."
docker-compose -f "$APP_DIR/docker-compose.yml" build

echo ""
echo "🚀 Starting services..."
docker-compose -f "$APP_DIR/docker-compose.yml" up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check if services are running
if docker-compose -f "$APP_DIR/docker-compose.yml" ps | grep -q "up"; then
    echo ""
    echo "✅ Application is running!"
    echo ""
    echo "🌐 Access the application at:"
    echo "   http://localhost (if running locally)"
    echo "   http://<your-nas-ip> (from other devices)"
    echo ""
    echo "📁 Downloads saved to: $DOWNLOAD_PATH"
    echo ""
    echo "📊 View logs:"
    echo "   docker-compose -f $APP_DIR/docker-compose.yml logs -f"
    echo ""
    echo "🛑 Stop services:"
    echo "   docker-compose -f $APP_DIR/docker-compose.yml stop"
else
    echo ""
    echo "❌ Services failed to start. Check logs:"
    docker-compose -f "$APP_DIR/docker-compose.yml" logs
    exit 1
fi