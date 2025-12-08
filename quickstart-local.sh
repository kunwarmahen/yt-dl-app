#!/bin/bash

##############################################################################
# YouTube to MP3 Downloader - Local Development Quickstart
# 
# This script sets up and runs the application locally WITHOUT Docker/Podman
# Perfect for development or users who prefer not to use containers
#
# Requirements:
#   - Python 3.8+
#   - Node.js 14+ (with npm)
#   - FFmpeg
#   - yt-dlp
#
# Usage: ./quickstart-local.sh [start|stop|status]
##############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOADS_DIR="${DOWNLOADS_DIR:-}"
BACKEND_PID_FILE="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# Log files
BACKEND_LOG="$SCRIPT_DIR/backend.log"
FRONTEND_LOG="$SCRIPT_DIR/frontend.log"

##############################################################################
# Helper Functions
##############################################################################

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

##############################################################################
# System Checks
##############################################################################

check_requirements() {
    print_header "Checking Requirements"
    
    local missing=0
    
    # Check Python
    if command -v python3 &> /dev/null; then
        local py_version=$(python3 --version 2>&1 | awk '{print $2}')
        print_success "Python 3 found: $py_version"
    else
        print_error "Python 3 not found. Please install Python 3.8+"
        missing=1
    fi
    
    # Check Node.js
    if command -v node &> /dev/null; then
        local node_version=$(node --version)
        print_success "Node.js found: $node_version"
    else
        print_error "Node.js not found. Please install Node.js 14+"
        missing=1
    fi
    
    # Check npm
    if command -v npm &> /dev/null; then
        local npm_version=$(npm --version)
        print_success "npm found: $npm_version"
    else
        print_error "npm not found. Please install npm"
        missing=1
    fi
    
    # Check FFmpeg
    if command -v ffmpeg &> /dev/null; then
        local ffmpeg_version=$(ffmpeg -version 2>&1 | head -n 1)
        print_success "FFmpeg found: $ffmpeg_version"
    else
        print_error "FFmpeg not found. Please install FFmpeg"
        missing=1
    fi
    
    # Check yt-dlp
    if command -v yt-dlp &> /dev/null; then
        local ydlp_version=$(yt-dlp --version)
        print_success "yt-dlp found: $ydlp_version"
    else
        print_warning "yt-dlp not found. Will install via pip"
    fi
    
    if [ $missing -eq 1 ]; then
        echo ""
        print_error "Missing dependencies. Please install the required packages."
        exit 1
    fi
    
    echo ""
    print_success "All requirements met!"
}

##############################################################################
# Setup Functions
##############################################################################

ask_downloads_location() {
    print_header "Configure Download Location"
    
    echo -e "Where would you like to save downloaded files?"
    echo -e "${YELLOW}Default: ./downloads${NC}"
    echo ""
    echo "Examples:"
    echo "  ./downloads"
    echo "  /home/user/my-downloads"
    echo "  /mnt/media/downloads"
    echo "  /Volumes/External-SSD/downloads"
    echo ""
    read -p "Enter path (or press Enter for default): " user_input
    
    if [ -z "$user_input" ]; then
        DOWNLOADS_DIR="$SCRIPT_DIR/downloads"
    else
        DOWNLOADS_DIR="$user_input"
    fi
    
    print_info "Download location set to: $DOWNLOADS_DIR"
    echo ""
}

setup_backend() {
    print_header "Setting Up Backend"
    
    if [ ! -d "$SCRIPT_DIR/backend" ]; then
        print_error "Backend directory not found at $SCRIPT_DIR/backend"
        exit 1
    fi
    
    cd "$SCRIPT_DIR/backend"
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        print_info "Creating Python virtual environment..."
        python3 -m venv venv
        print_success "Virtual environment created"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Install/upgrade dependencies
    print_info "Installing Python dependencies..."
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt > /dev/null 2>&1
    print_success "Python dependencies installed"
    
    echo ""
}

setup_frontend() {
    print_header "Setting Up Frontend"
    
    if [ ! -d "$SCRIPT_DIR/frontend" ]; then
        print_error "Frontend directory not found at $SCRIPT_DIR/frontend"
        exit 1
    fi
    
    cd "$SCRIPT_DIR/frontend"
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        print_info "Installing Node.js dependencies (first time, this may take a minute)..."
        npm install > /dev/null 2>&1
        print_success "Node.js dependencies installed"
    else
        print_success "Node.js dependencies already installed"
    fi
    
    echo ""
}

create_downloads_dir() {
    if [ ! -d "$DOWNLOADS_DIR" ]; then
        print_info "Creating downloads directory: $DOWNLOADS_DIR"
        mkdir -p "$DOWNLOADS_DIR"
        print_success "Downloads directory created"
    fi
}

##############################################################################
# Start/Stop Functions
##############################################################################

start_backend() {
    print_header "Starting Backend"
    
    if [ -f "$BACKEND_PID_FILE" ]; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_warning "Backend is already running (PID: $pid)"
            return
        fi
    fi
    
    cd "$SCRIPT_DIR/backend"
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Export download path to environment
    export DOWNLOAD_PATH="$DOWNLOADS_DIR"
    
    # Start backend
    print_info "Starting backend on http://localhost:$BACKEND_PORT"
    print_info "Logs: $BACKEND_LOG"
    
    nohup python3 -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
        > "$BACKEND_LOG" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$BACKEND_PID_FILE"
    
    # Wait for backend to be ready
    sleep 2
    
    if kill -0 "$pid" 2>/dev/null; then
        print_success "Backend started (PID: $pid)"
        echo ""
        return 0
    else
        print_error "Failed to start backend. Check $BACKEND_LOG for details"
        exit 1
    fi
}

start_frontend() {
    print_header "Starting Frontend"
    
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_warning "Frontend is already running (PID: $pid)"
            return
        fi
    fi
    
    cd "$SCRIPT_DIR/frontend"
    
    # Set environment variables for local development
    export REACT_APP_API_URL="http://localhost:$BACKEND_PORT"
    
    print_info "Starting frontend on http://localhost:$FRONTEND_PORT"
    print_info "Logs: $FRONTEND_LOG"
    print_info "API URL: $REACT_APP_API_URL"
    
    nohup npm start > "$FRONTEND_LOG" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$FRONTEND_PID_FILE"
    
    # Wait for frontend to start
    sleep 3
    
    if kill -0 "$pid" 2>/dev/null; then
        print_success "Frontend started (PID: $pid)"
        echo ""
        return 0
    else
        print_error "Failed to start frontend. Check $FRONTEND_LOG for details"
        exit 1
    fi
}

stop_backend() {
    if [ -f "$BACKEND_PID_FILE" ]; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_info "Stopping backend (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
            rm "$BACKEND_PID_FILE"
            print_success "Backend stopped"
        fi
    fi
}

stop_frontend() {
    # Kill all npm and node processes related to the frontend
    print_info "Stopping frontend..."
    
    # Kill by process name (most reliable for npm)
    pkill -f "npm start" 2>/dev/null || true
    pkill -f "node.*react" 2>/dev/null || true
    pkill -f "webpack" 2>/dev/null || true
    
    sleep 1
    
    # Force kill any remaining processes
    pkill -9 -f "npm start" 2>/dev/null || true
    pkill -9 -f "node.*react" 2>/dev/null || true
    
    # Clean up PID file
    rm -f "$FRONTEND_PID_FILE"
    
    print_success "Frontend stopped"
}

##############################################################################
# Status Functions
##############################################################################

check_status() {
    print_header "Application Status"
    
    # Check backend
    if [ -f "$BACKEND_PID_FILE" ]; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_success "Backend is running (PID: $pid)"
            print_info "→ http://localhost:$BACKEND_PORT"
        else
            print_error "Backend is not running (stale PID file)"
        fi
    else
        print_error "Backend is not running"
    fi
    
    # Check frontend
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_success "Frontend is running (PID: $pid)"
            print_info "→ http://localhost:$FRONTEND_PORT"
        else
            print_error "Frontend is not running (stale PID file)"
        fi
    else
        print_error "Frontend is not running"
    fi
    
    # Check downloads directory
    if [ -d "$DOWNLOADS_DIR" ]; then
        local file_count=$(find "$DOWNLOADS_DIR" -type f 2>/dev/null | wc -l)
        print_success "Downloads directory: $DOWNLOADS_DIR ($file_count files)"
    fi
    
    echo ""
}

##############################################################################
# Log Functions
##############################################################################

show_logs() {
    local service=$1
    
    case $service in
        backend)
            if [ -f "$BACKEND_LOG" ]; then
                echo -e "${BLUE}=== Backend Logs ===${NC}"
                tail -f "$BACKEND_LOG"
            else
                print_error "Backend log not found"
            fi
            ;;
        frontend)
            if [ -f "$FRONTEND_LOG" ]; then
                echo -e "${BLUE}=== Frontend Logs ===${NC}"
                tail -f "$FRONTEND_LOG"
            else
                print_error "Frontend log not found"
            fi
            ;;
        *)
            print_error "Unknown service: $service"
            echo "Usage: $0 logs [backend|frontend]"
            ;;
    esac
}

##############################################################################
# Main Commands
##############################################################################

start_all() {
    print_header "YouTube to MP3 Downloader - Local Setup"
    
    check_requirements
    ask_downloads_location
    create_downloads_dir
    setup_backend
    setup_frontend
    start_backend
    start_frontend
    
    print_header "✓ Application Started Successfully!"
    echo -e "${GREEN}Frontend:${NC} http://localhost:$FRONTEND_PORT"
    echo -e "${GREEN}Backend API:${NC} http://localhost:$BACKEND_PORT"
    echo -e "${GREEN}Downloads:${NC} $DOWNLOADS_DIR"
    echo ""
    echo -e "${YELLOW}Tip:${NC} To see logs, run:"
    echo "  $0 logs backend"
    echo "  $0 logs frontend"
    echo ""
    echo -e "${YELLOW}Tip:${NC} To stop, run: $0 stop"
    echo ""
}

stop_all() {
    print_header "Stopping Application"
    stop_backend
    stop_frontend
    echo ""
    print_success "Application stopped"
}

main() {
    local command=${1:-start}
    
    case $command in
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            stop_all
            sleep 2
            start_all
            ;;
        status)
            check_status
            ;;
        logs)
            show_logs "$2"
            ;;
        *)
            echo "YouTube to MP3 Downloader - Local Quickstart"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  start       - Start backend and frontend (default)"
            echo "  stop        - Stop backend and frontend"
            echo "  restart     - Restart the application"
            echo "  status      - Check application status"
            echo "  logs        - Show logs (usage: $0 logs [backend|frontend])"
            echo ""
            echo "Environment Variables:"
            echo "  BACKEND_PORT    - Backend port (default: 8000)"
            echo "  FRONTEND_PORT   - Frontend port (default: 3000)"
            echo "  DOWNLOADS_DIR   - Downloads directory (default: ./downloads)"
            echo ""
            echo "Examples:"
            echo "  ./quickstart-local.sh start"
            echo "  ./quickstart-local.sh status"
            echo "  BACKEND_PORT=9000 ./quickstart-local.sh start"
            echo "  ./quickstart-local.sh logs backend"
            echo ""
            ;;
    esac
}

# Run main
main "$@"