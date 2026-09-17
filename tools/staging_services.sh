#!/bin/bash
# staging_services.sh [P1-3 2026-09-01] - staging 4-service dependency-graph wrapper
# 解决 P0 已知问题:
#   - 直接 pkill -f python (Rule 1 违反, 误杀 risk)
#   - stop 顺序错 (先 core 后 unified, 留孤儿进程)
#   - restart 单服务时整组重启 (浪费 + 不必要停服务)
#
# 服务依赖图:
#   core_service(19200) <- log_service(19101)
#   core_service(19200) <- meta_backend(13011)    [共用 DB]
#   meta_backend(13011) <- unified_18081(18081)   [proxy]
#
# 拓扑序 start order: core -> log -> meta_backend -> unified
# 拓扑反序 stop order: unified -> meta_backend -> log -> core
#
# 用法:
#   staging_services.sh list
#   staging_services.sh status <name>
#   staging_services.sh health
#   staging_services.sh start [name|--all]
#   staging_services.sh stop  [name|--all]
#   staging_services.sh restart <name>
#   staging_services.sh restart-deps <name>    # 该服务 + 其上游依赖都重启
#   staging_services.sh topo                  # 打印依赖图
#
# 名字: core_service, log_service, meta_backend, unified_18081
set -u

BIN_DIR=/opt/app/staging/bin
DEPLOY_DIR=/opt/app/staging/deploy/current
LOG_DIR=/opt/app/staging/logs
PYTHON=/opt/miniconda3-py39/bin/python

# Service registry: name | port | script | log_file | env_kv_pairs (semicolon-separated KEY=VAL)
declare -A SVC_PORT=(
    [core_service]=19200
    [log_service]=19101
    [meta_backend]=13011
    [unified_18081]=18081
)
declare -A SVC_SCRIPT=(
    [core_service]=$BIN_DIR/core_service.py
    [log_service]=$BIN_DIR/log_service.py
    [meta_backend]=$DEPLOY_DIR/server.py
    [unified_18081]=$DEPLOY_DIR/unified_18081.py
)
declare -A SVC_LOG=(
    [core_service]=$LOG_DIR/core_service.log
    [log_service]=$LOG_DIR/log_service.log
    [meta_backend]=$LOG_DIR/backend.log
    [unified_18081]=$LOG_DIR/unified_server.log
)

# Dependency graph: "<service>|<upstream1>,<upstream2>"
# Topological start order: core_service -> log_service -> meta_backend -> unified_18081
START_ORDER=(core_service log_service meta_backend unified_18081)
declare -A SVC_DEPS=(
    [core_service]=""
    [log_service]="core_service"
    [meta_backend]="core_service"
    [unified_18081]="meta_backend"
)

# Build env block per service
build_env() {
    local name=$1
    case $name in
        core_service)
            echo "CORE_SERVICE_PORT=19200 CORE_SERVICE_BIND=0.0.0.0 CORE_SERVICE_DB_PATH=/opt/app/staging/meta/architecture.db CORE_SERVICE_SECRET=staging-v007.49-d"
            ;;
        log_service)
            echo "LOG_SERVICE_PORT=19101 LOG_SERVICE_DB_PATH=/opt/app/staging/meta/architecture.db"
            ;;
        meta_backend)
            echo "PORT=13011 SQLITE_DB_PATH=/opt/app/staging/meta/architecture.db ARCH_DB_PATH=/opt/app/staging/meta/architecture.db FLASK_DEBUG=true FLASK_SECRET_KEY=staging-flask-key-2026-07-14-staging-secret JWT_SECRET_KEY=staging-jwt-secret-2026-07-14-staging-jwt"
            ;;
        unified_18081)
            echo "BACKEND_PORT=13011"
            ;;
        *)
            echo "[ERROR] unknown service: $name" >&2
            return 1
            ;;
    esac
}

# Get PID of service by exact port match using ss (with ps fallback for non-root)
get_pid() {
    local name=$1
    local port=${SVC_PORT[$name]:-}
    local script=${SVC_SCRIPT[$name]:-}
    [ -z "$port" ] && return 1
    # Method 1: ss with pid (root or CAP_NET_ADMIN)
    local pid=$(ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $0}' | grep -oP 'pid=\K[0-9]+' | head -1)
    if [ -n "$pid" ]; then
        echo "$pid"
        return 0
    fi
    # Method 2: ss check if port LISTEN at all (port open but no owner pid)
    if ss -tln 2>/dev/null | awk -v p=":$port" '$4 ~ p' | grep -q LISTEN; then
        # Port is listening but we can't see owner. Match by script path via ps.
        if [ -n "$script" ]; then
            # Try to find a python process with this script in cmdline
            local script_basename=$(basename "$script" 2>/dev/null)
            if [ -n "$script_basename" ]; then
                pid=$(ps -eo pid,cmd 2>/dev/null | grep -F "$script_basename" | grep -v grep | awk '{print $1}' | head -1)
                if [ -n "$pid" ]; then
                    echo "$pid"
                    return 0
                fi
            fi
        fi
        # Port is listening, we just can't see PID (non-root) - report port-only state
        echo "?"
        return 0
    fi
    # Port not listening at all
    return 1
}

# Print service status
status_one() {
    local name=$1
    local port=${SVC_PORT[$name]:-}
    local script=${SVC_SCRIPT[$name]:-}
    local log=${SVC_LOG[$name]:-}
    local pid=$(get_pid $name)
    local pid_exit=$?
    if [ $pid_exit -eq 0 ] && [ -n "$pid" ] && [ "$pid" != "?" ]; then
        printf "%-18s port=%-6s pid=%-8s state=ALIVE   script=%s\n" "$name" "$port" "$pid" "$script"
    elif [ $pid_exit -eq 0 ]; then
        # Port listening but PID unknown (non-root ss)
        printf "%-18s port=%-6s pid=?         state=ALIVE_NOPID  script=%s\n" "$name" "$port" "$script"
    else
        printf "%-18s port=%-6s pid=-        state=DEAD    script=%s\n" "$name" "$port" "$script"
    fi
}

cmd_list() {
    echo "=== staging services ==="
    for s in "${START_ORDER[@]}"; do
        status_one "$s"
    done
}

cmd_status() {
    local name=${1:-}
    if [ -z "$name" ]; then
        echo "usage: staging_services.sh status <name>" >&2
        return 2
    fi
    if [ -z "${SVC_PORT[$name]:-}" ]; then
        echo "[ERROR] unknown service: $name" >&2
        echo "valid: ${!SVC_PORT[*]}" >&2
        return 2
    fi
    status_one "$name"
    local port=${SVC_PORT[$name]}
    local pid=$(get_pid $name)
    echo "  port=$port pid=$pid log=${SVC_LOG[$name]}"
    if [ -n "$pid" ] && [ -f "${SVC_LOG[$name]}" ]; then
        echo "  --- last 5 log lines ---"
        tail -5 "${SVC_LOG[$name]}" | sed 's/^/    /'
    fi
}

cmd_health() {
    echo "=== health check ==="
    local fail=0
    for s in "${START_ORDER[@]}"; do
        local port=${SVC_PORT[$s]}
        local pid=$(get_pid $s)
        local pid_exit=$?
        local http_code=""
        # Try a 3s HTTP probe (port 18081 has /api/v1/auth/dev-login; others may 404 on / which is fine)
        http_code=$(curl -s -o /dev/null --max-time 3 -w "%{http_code}" "http://127.0.0.1:$port/" 2>/dev/null || echo "000")
        # Service is "up" if: port is listening (pid_exit==0) AND HTTP responds (code != 000)
        if [ $pid_exit -eq 0 ] && [ "$http_code" != "000" ]; then
            printf "  %-18s pid=%-8s http=%s  OK\n" "$s" "${pid:--}" "$http_code"
        else
            printf "  %-18s pid=%-8s http=%s  FAIL\n" "$s" "${pid:--}" "$http_code"
            fail=$((fail+1))
        fi
    done
    if [ $fail -gt 0 ]; then
        echo "HEALTH_FAIL: $fail service(s) down"
        return 1
    fi
    echo "HEALTH_OK"
}

# Start one service (no deps)
start_one() {
    local name=$1
    local pid=$(get_pid $name)
    if [ -n "$pid" ]; then
        echo "[SKIP] $name already running pid=$pid"
        return 0
    fi
    local script=${SVC_SCRIPT[$name]}
    local log=${SVC_LOG[$name]}
    mkdir -p "$LOG_DIR"
    local env_block=$(build_env $name)
    # Use setsid+nohup so service survives script exit
    setsid nohup env $env_block $PYTHON "$script" >> "$log" 2>&1 < /dev/null &
    local new_pid=$!
    disown $new_pid 2>/dev/null
    echo "[START] $name pid=$new_pid script=$script log=$log"
}

# Start service + upstream deps recursively (topo order)
start_with_deps() {
    local name=$1
    local deps=${SVC_DEPS[$name]:-}
    if [ -n "$deps" ]; then
        IFS=',' read -ra dep_arr <<< "$deps"
        for d in "${dep_arr[@]}"; do
            start_with_deps "$d"
        done
    fi
    start_one "$name"
    # Give service a few seconds to bind port
    sleep 2
}

cmd_start() {
    local target=${1:-}
    if [ -z "$target" ] || [ "$target" = "--all" ]; then
        # Start everything in topo order
        for s in "${START_ORDER[@]}"; do
            start_one "$s"
            sleep 2
        done
    else
        if [ -z "${SVC_PORT[$target]:-}" ]; then
            echo "[ERROR] unknown service: $target" >&2
            return 2
        fi
        start_with_deps "$target"
    fi
}

# Kill one service by exact PID on its port (Rule 1 compliant: no pkill -f)
stop_one() {
    local name=$1
    local pid=$(get_pid $name)
    local pid_exit=$?
    if [ $pid_exit -ne 0 ]; then
        echo "[SKIP] $name not running (port not listening)"
        return 0
    fi
    if [ -z "$pid" ] || [ "$pid" = "?" ]; then
        # Port listening but we can't see PID. Can't safely kill.
        echo "[FAIL] $name port listening but PID unknown (non-root ss?). Refusing to kill." >&2
        echo "[FAIL] Run with sudo, or kill via known PID" >&2
        return 1
    fi
    local port=${SVC_PORT[$name]}
    # Defensive: verify PID is actually on this port before killing (avoids wrong PID)
    if ! ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p' | grep -q "pid=$pid"; then
        echo "[FAIL] PID $pid is NOT on port $port for $name, ABORT" >&2
        return 1
    fi
    kill -TERM "$pid" 2>/dev/null
    # Wait up to 5s for graceful exit
    for i in 1 2 3 4 5; do
        sleep 1
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "[STOP] $name pid=$pid (graceful)"
            return 0
        fi
    done
    # Force kill
    kill -9 "$pid" 2>/dev/null
    echo "[STOP] $name pid=$pid (forced)"
}

cmd_stop() {
    local target=${1:-}
    if [ -z "$target" ] || [ "$target" = "--all" ]; then
        # Stop everything in REVERSE topo order, BUT skip core_service (it is our control channel)
        # To stop core_service, the operator must SSH into the box manually (P0 known gap)
        echo "[WARN] stop --all: SKIPPING core_service (it's the /api/exec control channel)"
        echo "[WARN] to fully stop core, you need direct shell access to staging"
        for ((i=${#START_ORDER[@]}-1; i>=0; i--)); do
            if [ "${START_ORDER[$i]}" = "core_service" ]; then
                continue
            fi
            stop_one "${START_ORDER[$i]}"
        done
    else
        if [ -z "${SVC_PORT[$target]:-}" ]; then
            echo "[ERROR] unknown service: $target" >&2
            return 2
        fi
        if [ "$target" = "core_service" ]; then
            echo "[REFUSE] cannot stop core_service via this channel (would kill /api/exec)" >&2
            echo "[REFUSE] SSH to staging manually: pkill -f /opt/app/staging/bin/core_service.py" >&2
            return 3
        fi
        stop_one "$target"
    fi
}

cmd_restart() {
    local target=${1:-}
    if [ -z "$target" ]; then
        echo "usage: staging_services.sh restart <name>" >&2
        return 2
    fi
    if [ -z "${SVC_PORT[$target]:-}" ]; then
        echo "[ERROR] unknown service: $target" >&2
        return 2
    fi
    stop_one "$target"
    sleep 1
    start_with_deps "$target"
}

# Restart service + upstream deps
cmd_restart_deps() {
    local target=${1:-}
    if [ -z "$target" ]; then
        echo "usage: staging_services.sh restart-deps <name>" >&2
        return 2
    fi
    if [ -z "${SVC_PORT[$target]:-}" ]; then
        echo "[ERROR] unknown service: $target" >&2
        return 2
    fi
    # Collect all deps (transitive) in topo order, including target
    local to_restart=()
    local visited=""
    _collect_deps() {
        local n=$1
        if [[ " $visited " == *" $n "* ]]; then return; fi
        visited="$visited $n"
        local deps=${SVC_DEPS[$n]:-}
        if [ -n "$deps" ]; then
            IFS=',' read -ra dep_arr <<< "$deps"
            for d in "${dep_arr[@]}"; do
                _collect_deps "$d"
            done
        fi
        to_restart+=("$n")
    }
    _collect_deps "$target"
    echo "[restart-deps] order: ${to_restart[*]}"
    # Stop in reverse topo
    for ((i=${#to_restart[@]}-1; i>=0; i--)); do
        stop_one "${to_restart[$i]}"
    done
    sleep 1
    # Start in topo
    for s in "${to_restart[@]}"; do
        start_one "$s"
        sleep 2
    done
}

cmd_topo() {
    echo "=== staging service dependency graph ==="
    echo "  core_service (19200)         <- root"
    echo "  log_service  (19101)         <- core_service"
    echo "  meta_backend (13011)         <- core_service (shared DB)"
    echo "  unified_18081 (18081)        <- meta_backend (proxy)"
    echo ""
    echo "  start order: core_service -> log_service -> meta_backend -> unified_18081"
    echo "  stop  order: unified_18081 -> meta_backend -> log_service -> core_service"
}

cmd_help() {
    cat <<EOF
staging_services.sh - staging 4-service dependency-graph wrapper

usage:
  staging_services.sh list
  staging_services.sh status <name>
  staging_services.sh health
  staging_services.sh start  [name|--all]    # default: --all
  staging_services.sh stop   [name|--all]    # default: --all
  staging_services.sh restart <name>
  staging_services.sh restart-deps <name>    # target + transitive deps
  staging_services.sh topo                   # print dependency graph
  staging_services.sh help

services: ${START_ORDER[*]}
EOF
}

# Dispatch
case "${1:-help}" in
    list)              shift; cmd_list "$@" ;;
    status)            shift; cmd_status "$@" ;;
    health)            shift; cmd_health "$@" ;;
    start)             shift; cmd_start "$@" ;;
    stop)              shift; cmd_stop "$@" ;;
    restart)           shift; cmd_restart "$@" ;;
    restart-deps)      shift; cmd_restart_deps "$@" ;;
    topo)              shift; cmd_topo "$@" ;;
    help|-h|--help)    cmd_help ;;
    *)                 echo "[ERROR] unknown command: $1" >&2; cmd_help; exit 2 ;;
esac
