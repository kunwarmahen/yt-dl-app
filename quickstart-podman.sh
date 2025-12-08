#!/bin/bash

# YouTube MP3 Downloader - Podman Quick Start Script

set -e

echo "🎵 YouTube MP3 Downloader - Podman Setup"
echo "========================================"
echo ""

# Check if Podman is installed
if ! command -v podman &> /dev/null; then
    echo "❌ Podman is not installed."
    echo "Please install Podman first:"
    echo "  https://podman.io/docs/installation"
    exit 1
fi

# Check podman compose (built-in subcommand)
if ! podman compose version &> /dev/null; then
    echo "❌ 'podman compose' not available."
    echo "Podman 3.0+ is required with built-in 'podman compose' support."
    echo "Install Podman 3.0 or later from:"
    echo "  https://podman.io/docs/installation"
    exit 1
fi

echo "✅ Podman found: $(podman --version)"
echo "✅ podman compose available: $(podman compose version 2>/dev/null || echo 'built-in')"
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
    DOWNLOAD_PATH="/mnt/downloads"
    echo "Using default: $DOWNLOAD_PATH"
fi

# Create download directory if it doesn't exist
echo "📁 Creating download directory..."
mkdir -p "$DOWNLOAD_PATH" 2>/dev/null || echo "⚠️  Could not create directory. Please ensure it exists and is writable."

# Generate docker-compose.yml from template
echo "⚙️  Generating docker-compose.yml from template..."
cp "$APP_DIR/docker-compose.yml.template" "$APP_DIR/docker-compose.yml"

# Update docker-compose.yml with the custom path
echo "⚙️  Updating configuration..."

# Escape special characters for sed
ESCAPED_PATH=$(printf '%s\n' "$DOWNLOAD_PATH" | sed -e 's/[\/&]/\\&/g')

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s|PLACEHOLDER_PATH|$ESCAPED_PATH|g" "$APP_DIR/docker-compose.yml"
else
    # Linux
    sed -i "s|PLACEHOLDER_PATH|$ESCAPED_PATH|g" "$APP_DIR/docker-compose.yml"
fi

# Verify replacement worked
if grep -q "PLACEHOLDER_PATH" "$APP_DIR/docker-compose.yml"; then
    echo "❌ Error: Failed to replace path placeholder"
    exit 1
fi

echo "✅ docker-compose.yml created with download path: $DOWNLOAD_PATH"
echo ""

echo "🔨 Building container images with Podman..."
podman compose -f "$APP_DIR/docker-compose.yml" build

echo ""
echo "🚀 Starting services with Podman..."
podman compose -f "$APP_DIR/docker-compose.yml" up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check if services are running
if podman compose -f "$APP_DIR/docker-compose.yml" ps | grep -q "Up"; then
    echo ""
    echo "✅ Application is running with Podman!"
    echo ""
    echo "🌐 Access the application at:"
    echo "   http://localhost (if running locally)"
    echo "   http://<your-nas-ip> (from other devices)"
    echo ""
    echo "📁 Downloads saved to: $DOWNLOAD_PATH"
    echo ""
    echo "📊 View logs:"
    echo "   podman compose -f $APP_DIR/docker-compose.yml logs -f"
    echo ""
    echo "🛑 Stop services:"
    echo "   podman compose -f $APP_DIR/docker-compose.yml stop"
    echo ""
    echo "💡 For more Podman information, see README.md"
else
    echo ""
    echo "❌ Services failed to start. Check logs:"
    podman compose -f "$APP_DIR/docker-compose.yml" logs
    exit 1
fi