#!/bin/bash

# Wan S2V API Server Startup Script
# This script provides easy management of the Flask API server

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_HOST="127.0.0.1"
DEFAULT_PORT="5000"
DEFAULT_LOG_LEVEL="INFO"
ENV_FILE=".env"
REQUIREMENTS_FILE="requirements_r2_api.txt"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Python version
check_python() {
    print_status "Checking Python version..."
    
    if ! command_exists python3; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    required_version="3.10"
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
        print_error "Python $required_version or higher is required. Found: $python_version"
        exit 1
    fi
    
    print_success "Python $python_version is compatible"
}

# Function to check and install dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        print_error "Requirements file not found: $REQUIREMENTS_FILE"
        exit 1
    fi
    
    # Check if virtual environment is recommended
    if [ -z "$VIRTUAL_ENV" ]; then
        print_warning "Not running in a virtual environment. Consider using venv or conda."
    fi
    
    # Install dependencies
    print_status "Installing Python dependencies..."
    python3 -m pip install -r "$REQUIREMENTS_FILE" --quiet
    
    print_success "Dependencies installed successfully"
}

# Function to check environment configuration
check_environment() {
    print_status "Checking environment configuration..."
    
    if [ ! -f "$ENV_FILE" ]; then
        print_warning "Environment file not found: $ENV_FILE"
        print_status "Creating from example..."
        
        if [ -f ".env.example" ]; then
            cp .env.example "$ENV_FILE"
            print_warning "Please edit $ENV_FILE with your R2 credentials before starting the server"
            return 1
        else
            print_error "No .env.example file found"
            return 1
        fi
    fi
    
    # Check required environment variables
    source "$ENV_FILE"
    
    required_vars=("R2_ENDPOINT_URL" "R2_ACCESS_KEY_ID" "R2_SECRET_ACCESS_KEY")
    missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        print_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        print_warning "Please update $ENV_FILE with your configuration"
        return 1
    fi
    
    print_success "Environment configuration is valid"
    return 0
}

# Function to check model checkpoints
check_model() {
    print_status "Checking model checkpoints..."
    
    # Load checkpoint directory from environment
    source "$ENV_FILE" 2>/dev/null || true
    ckpt_dir="${WAN_CKPT_DIR:-./Wan2.2-S2V-14B/}"
    
    if [ ! -d "$ckpt_dir" ]; then
        print_warning "Model checkpoint directory not found: $ckpt_dir"
        print_warning "Please ensure the Wan S2V 14B model is available"
        return 1
    fi
    
    print_success "Model checkpoint directory found: $ckpt_dir"
    return 0
}

# Function to start the server
start_server() {
    local host="${1:-$DEFAULT_HOST}"
    local port="${2:-$DEFAULT_PORT}"
    local log_level="${3:-$DEFAULT_LOG_LEVEL}"
    local debug_mode="$4"
    
    print_status "Starting Wan S2V API Server..."
    print_status "Host: $host"
    print_status "Port: $port"
    print_status "Log Level: $log_level"
    
    # Build command arguments
    cmd_args=("--host" "$host" "--port" "$port" "--log-level" "$log_level")
    
    if [ "$debug_mode" = "true" ]; then
        cmd_args+=("--debug")
        print_status "Debug mode: enabled"
    fi
    
    # Create workspace directory
    workspace_dir="${WORKSPACE_DIR:-workspace}"
    mkdir -p "$workspace_dir"
    
    print_success "Server starting at http://$host:$port"
    print_status "Press Ctrl+C to stop the server"
    print_status ""
    
    # Start the server
    python3 app.py "${cmd_args[@]}"
}

# Function to test the server
test_server() {
    local server_url="${1:-http://127.0.0.1:5000}"
    
    print_status "Testing server at $server_url..."
    
    if command_exists python3; then
        python3 test_client.py --server "$server_url" --health-only
    else
        print_error "Python 3 not found for testing"
        return 1
    fi
}

# Function to show usage
show_usage() {
    echo "Wan S2V API Server Management Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start                Start the API server (default)"
    echo "  check                Check system requirements and configuration" 
    echo "  install              Install dependencies"
    echo "  test                 Test the server with health check"
    echo "  help                 Show this help message"
    echo ""
    echo "Start Options:"
    echo "  --host HOST         Host to bind to (default: $DEFAULT_HOST)"
    echo "  --port PORT         Port to bind to (default: $DEFAULT_PORT)"
    echo "  --log-level LEVEL   Log level (default: $DEFAULT_LOG_LEVEL)"
    echo "  --debug             Enable debug mode"
    echo ""
    echo "Test Options:"
    echo "  --server URL        Server URL to test (default: http://127.0.0.1:5000)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Start server with defaults"
    echo "  $0 start --host 0.0.0.0 --port 8080  # Start on all interfaces, port 8080"
    echo "  $0 check                              # Check system requirements"
    echo "  $0 test                               # Test local server"
    echo "  $0 test --server http://gpu-server:5000  # Test remote server"
}

# Main script logic
main() {
    local command="${1:-start}"
    
    case "$command" in
        "start")
            shift
            
            # Parse start options
            host="$DEFAULT_HOST"
            port="$DEFAULT_PORT"
            log_level="$DEFAULT_LOG_LEVEL"
            debug_mode="false"
            
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --host)
                        host="$2"
                        shift 2
                        ;;
                    --port)
                        port="$2"
                        shift 2
                        ;;
                    --log-level)
                        log_level="$2"
                        shift 2
                        ;;
                    --debug)
                        debug_mode="true"
                        shift
                        ;;
                    *)
                        print_error "Unknown option: $1"
                        show_usage
                        exit 1
                        ;;
                esac
            done
            
            # Run checks
            check_python
            check_dependencies
            if ! check_environment; then
                exit 1
            fi
            check_model  # Warning only, don't exit
            
            # Start server
            start_server "$host" "$port" "$log_level" "$debug_mode"
            ;;
            
        "check")
            print_status "Running system checks..."
            check_python
            check_dependencies  
            check_environment
            check_model
            print_success "All checks completed"
            ;;
            
        "install")
            print_status "Installing dependencies..."
            check_python
            check_dependencies
            print_success "Installation completed"
            ;;
            
        "test")
            shift
            server_url="http://127.0.0.1:5000"
            
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --server)
                        server_url="$2"
                        shift 2
                        ;;
                    *)
                        print_error "Unknown option: $1"
                        show_usage
                        exit 1
                        ;;
                esac
            done
            
            test_server "$server_url"
            ;;
            
        "help"|"--help"|"-h")
            show_usage
            ;;
            
        *)
            print_error "Unknown command: $command"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"