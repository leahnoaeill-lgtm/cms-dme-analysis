#!/bin/bash
#
# CMS DME Analysis Dashboard Startup Script
# Starts PostgreSQL and Flask dashboard services
#
# Usage: ./start_dashboard.sh [--stop] [--status]
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_PORT=5001
POSTGRES_PORT=5432
LOG_FILE="$SCRIPT_DIR/dashboard.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if PostgreSQL is running
check_postgres() {
    /Applications/Postgres.app/Contents/Versions/latest/bin/pg_isready -h localhost -p $POSTGRES_PORT > /dev/null 2>&1
    return $?
}

# Check if dashboard is running
check_dashboard() {
    lsof -ti:$DASHBOARD_PORT > /dev/null 2>&1
    return $?
}

# Start PostgreSQL
start_postgres() {
    if check_postgres; then
        print_status "PostgreSQL is already running on port $POSTGRES_PORT"
        return 0
    fi

    print_warning "Starting PostgreSQL..."
    open -a Postgres

    # Wait for PostgreSQL to start (max 30 seconds)
    for i in {1..30}; do
        if check_postgres; then
            print_status "PostgreSQL started successfully"
            return 0
        fi
        sleep 1
    done

    print_error "Failed to start PostgreSQL after 30 seconds"
    return 1
}

# Start Dashboard
start_dashboard() {
    if check_dashboard; then
        print_status "Dashboard is already running on port $DASHBOARD_PORT"
        echo "    URL: http://localhost:$DASHBOARD_PORT"
        return 0
    fi

    print_warning "Starting Dashboard..."
    cd "$SCRIPT_DIR"
    nohup python3 dashboard.py > "$LOG_FILE" 2>&1 &
    DASHBOARD_PID=$!

    # Wait for dashboard to start (max 10 seconds)
    for i in {1..10}; do
        if check_dashboard; then
            print_status "Dashboard started successfully (PID: $DASHBOARD_PID)"
            echo "    URL: http://localhost:$DASHBOARD_PORT"
            echo "    Log: $LOG_FILE"
            return 0
        fi
        sleep 1
    done

    print_error "Failed to start Dashboard after 10 seconds"
    print_error "Check log file: $LOG_FILE"
    return 1
}

# Stop services
stop_services() {
    echo "Stopping services..."

    if check_dashboard; then
        print_warning "Stopping Dashboard..."
        lsof -ti:$DASHBOARD_PORT | xargs kill -9 2>/dev/null
        print_status "Dashboard stopped"
    else
        print_status "Dashboard is not running"
    fi

    echo ""
    print_warning "Note: PostgreSQL (Postgres.app) must be stopped manually from the menu bar"
}

# Show status
show_status() {
    echo "=========================================="
    echo "CMS DME Analysis Dashboard Status"
    echo "=========================================="
    echo ""

    if check_postgres; then
        print_status "PostgreSQL: Running on port $POSTGRES_PORT"
    else
        print_error "PostgreSQL: Not running"
    fi

    if check_dashboard; then
        PID=$(lsof -ti:$DASHBOARD_PORT)
        print_status "Dashboard:  Running on port $DASHBOARD_PORT (PID: $PID)"
        echo "    URL: http://localhost:$DASHBOARD_PORT"
    else
        print_error "Dashboard:  Not running"
    fi

    echo ""
}

# Main
case "${1:-}" in
    --stop)
        stop_services
        ;;
    --status)
        show_status
        ;;
    --help|-h)
        echo "CMS DME Analysis Dashboard Startup Script"
        echo ""
        echo "Usage: $0 [option]"
        echo ""
        echo "Options:"
        echo "  (none)     Start PostgreSQL and Dashboard"
        echo "  --stop     Stop the Dashboard service"
        echo "  --status   Show status of all services"
        echo "  --help     Show this help message"
        echo ""
        echo "Path: $SCRIPT_DIR/start_dashboard.sh"
        ;;
    *)
        echo "=========================================="
        echo "CMS DME Analysis Dashboard Startup"
        echo "=========================================="
        echo ""

        # Start PostgreSQL first
        if ! start_postgres; then
            print_error "Cannot continue without PostgreSQL"
            exit 1
        fi

        echo ""

        # Start Dashboard
        if ! start_dashboard; then
            exit 1
        fi

        echo ""
        echo "=========================================="
        print_status "All services started successfully!"
        echo "=========================================="
        ;;
esac
