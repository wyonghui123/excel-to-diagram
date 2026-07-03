#!/usr/bin/env bash
# ============================================================
# precheck_remote.sh - Remote deployment pre-check (PHASE 0)
# ============================================================
# 用途: 远程执行, 输出"事实报告"作为部署前的真相
# 设计: 不做预测, 只采集事实
# 用法:
#   ssh root@172.20.59.7 'bash -s' < tools/precheck_remote.sh
#   # 或在远端:
#   bash /opt/app/tools/precheck_remote.sh
# ============================================================

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 输出分隔
hr() { echo -e "${CYAN}============================================================${NC}"; }
section() { echo -e "\n${YELLOW}## $1${NC}"; }
kv() { echo -e "${GREEN}$1:${NC} $2"; }

# ============================================================
# HEADER
# ============================================================
hr
echo -e "${CYAN}  REMOTE DEPLOYMENT PRE-CHECK (PHASE 0)${NC}"
echo -e "${CYAN}  Host:    $(hostname -f 2>/dev/null || hostname)${NC}"
echo -e "${CYAN}  Time:    $(date -Iseconds 2>/dev/null || date)${NC}"
echo -e "${CYAN}  OS:      $(uname -a 2>/dev/null || echo 'unknown')${NC}"
echo -e "${CYAN}  User:    $(whoami 2>/dev/null || echo 'unknown')${NC}"
hr

# ============================================================
# 1. SYSTEMD SERVICES
# ============================================================
section "1. Systemd Services (excel/yonaa/diagram)"
if command -v systemctl >/dev/null 2>&1; then
    ls /etc/systemd/system/*.service 2>/dev/null | grep -iE "excel|yonaa|diagram|arch|backend|frontend" | while read svc; do
        name=$(basename "$svc")
        active=$(systemctl is-active "$name" 2>/dev/null || echo "unknown")
        enabled=$(systemctl is-enabled "$name" 2>/dev/null || echo "unknown")
        mainpid=$(systemctl show "$name" --property=MainPID --value 2>/dev/null)
        echo -e "  ${name}: active=${active}, enabled=${enabled}, MainPID=${mainpid}"
        echo "  ---- Config:"
        cat "$svc" 2>/dev/null | sed 's/^/    /'
        echo "  ---- Last 5 journal entries:"
        journalctl -u "$name" --no-pager -n 5 2>/dev/null | sed 's/^/    /' || echo "    (no journal)"
        echo ""
    done
else
    echo "  systemctl not found (可能不是 systemd 系统)"
fi

# ============================================================
# 2. PYTHON LOCATIONS
# ============================================================
section "2. Python Interpreters Found"
which python python3 python2 2>/dev/null
ls /usr/bin/python* 2>/dev/null
ls /usr/local/bin/python* 2>/dev/null
ls /opt/*/bin/python* 2>/dev/null
ls /opt/miniconda*/bin/python* 2>/dev/null
ls /opt/conda*/bin/python* 2>/dev/null
ls /tmp/python-build/Python-*/python 2>/dev/null
echo ""
echo "  /opt/app/venv/bin/python: $(ls -la /opt/app/venv/bin/python 2>/dev/null || echo 'NOT FOUND')"
echo "  /opt/miniconda3-py39/bin/python: $(ls -la /opt/miniconda3-py39/bin/python 2>/dev/null || echo 'NOT FOUND')"

# ============================================================
# 3. DIRECTORY STRUCTURE
# ============================================================
section "3. Directory Structure"
echo "--- /opt/app/ ---"
ls -la /opt/app/ 2>/dev/null || echo "  (no /opt/app/)"
echo ""
echo "--- /opt/app/deployments/ ---"
ls -la /opt/app/deployments/ 2>/dev/null || echo "  (no deployments/)"
echo ""
echo "--- /opt/app/current (symlink) ---"
ls -la /opt/app/current 2>/dev/null || echo "  (no current)"
echo ""
echo "--- /opt/app/shared/ ---"
ls -la /opt/app/shared/ 2>/dev/null || echo "  (no shared/)"
echo ""
echo "--- /opt/app/meta/ ---"
ls -la /opt/app/meta/ 2>/dev/null || echo "  (no /opt/app/meta/)"
echo ""

# ============================================================
# 4. CURRENT DEPLOYMENT CONTENTS
# ============================================================
section "4. Current Deployment (resolve /opt/app/current)"
if [ -L /opt/app/current ]; then
    CURRENT=$(readlink -f /opt/app/current)
    echo "  /opt/app/current -> ${CURRENT}"
    if [ -d "$CURRENT" ]; then
        echo "  --- Contents (top-level) ---"
        ls -la "$CURRENT" | head -30
        echo ""
        echo "  --- server.py presence ---"
        ls -la "$CURRENT/server.py" 2>/dev/null
        ls -la "$CURRENT/backend/server.py" 2>/dev/null
        ls -la "$CURRENT/meta/server.py" 2>/dev/null
        echo ""
        echo "  --- architecture.db presence ---"
        ls -la "$CURRENT/architecture.db" 2>/dev/null
        ls -la "$CURRENT/backend/architecture.db" 2>/dev/null
        ls -la "$CURRENT/meta/architecture.db" 2>/dev/null
    fi
fi
echo ""
echo "--- /opt/app/deployments/*/backend/ ---"
for d in /opt/app/deployments/*/; do
    if [ -d "$d" ]; then
        echo "  $d"
        ls "$d" 2>/dev/null | head -10 | sed 's/^/    /'
    fi
done

# ============================================================
# 5. RUNNING PROCESSES
# ============================================================
section "5. Running Python Processes"
ps -ef | grep -E "python.*server" | grep -v grep | while read line; do
    echo "  $line"
done
echo ""
echo "--- Process Working Directories ---"
for pid in $(ps -ef | grep "python.*server" | grep -v grep | awk '{print $2}'); do
    cwd=$(readlink /proc/$pid/cwd 2>/dev/null || echo "unknown")
    cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
    echo "  PID $pid: cwd=$cwd"
    echo "    cmdline: $cmdline"
done

# ============================================================
# 6. PORT LISTENERS
# ============================================================
section "6. TCP Port Listeners (8080-9000, 5000-5010)"
if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | grep -E ":(5000|5001|8080|8081)" || echo "  (no listeners in 5000/5001/8080/8081)"
else
    netstat -tlnp 2>/dev/null | grep -E ":(5000|5001|8080|8081)" || echo "  (no listeners)"
fi
echo ""
echo "--- All non-localhost LISTEN ---"
ss -tln 2>/dev/null | head -20 || netstat -tln 2>/dev/null | head -20

# ============================================================
# 7. DATABASE FILES
# ============================================================
section "7. Database Files"
find /opt/app -name "*.db" -type f 2>/dev/null | while read db; do
    size=$(stat -c%s "$db" 2>/dev/null)
    mtime=$(stat -c%y "$db" 2>/dev/null)
    echo "  $db (${size} bytes, ${mtime})"
done
echo ""

# ============================================================
# 8. KEY API HEALTH
# ============================================================
section "8. Quick API Health Check (curl)"
for port in 5000 5001 8080 8081; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:${port}/" 2>/dev/null || echo "CONN_REFUSED")
    echo "  Port ${port}/  -> ${code}"
done
echo ""
echo "--- /api/v1/health (if backend responding) ---"
for port in 5000 5001; do
    body=$(curl -s --max-time 3 "http://localhost:${port}/api/v1/health" 2>/dev/null || echo "CONN_REFUSED")
    echo "  Port ${port}/api/v1/health: ${body}"
done

# ============================================================
# 9. KEY PYTHON IMPORTS IN server.py
# ============================================================
section "9. Key imports in server.py (current deployment)"
if [ -L /opt/app/current ]; then
    CURRENT=$(readlink -f /opt/app/current)
    for sp in "$CURRENT/server.py" "$CURRENT/backend/server.py" "$CURRENT/meta/server.py"; do
        if [ -f "$sp" ]; then
            echo "  --- $sp ---"
            grep -E "^(from|import)" "$sp" | head -30 | sed 's/^/    /'
            break
        fi
    done
fi
echo ""
echo "--- v003 import sample ---"
for sp in /opt/app/deployments/v20260630_003/backend/server.py /opt/app/deployments/v20260630_003/meta/server.py /opt/app/meta/server.py; do
    if [ -f "$sp" ]; then
        echo "  --- $sp ---"
        grep -E "^(from|import)" "$sp" | head -20 | sed 's/^/    /'
        echo ""
    fi
done

# ============================================================
# 10. DB ENUM MUTABILITY STATE
# ============================================================
section "10. Enum Mutability in Database(s)"
for db in /opt/app/deployments/*/backend/architecture.db /opt/app/deployments/*/meta/architecture.db /opt/app/meta/architecture.db; do
    if [ -f "$db" ]; then
        if command -v sqlite3 >/dev/null 2>&1; then
            has_enum=$(sqlite3 "$db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='enum_types';" 2>/dev/null || echo "0")
            if [ "$has_enum" = "1" ]; then
                mut=$(sqlite3 "$db" "SELECT DISTINCT mutability, COUNT(*) FROM enum_types GROUP BY mutability;" 2>/dev/null | tr '\n' '|')
                count=$(sqlite3 "$db" "SELECT COUNT(*) FROM enum_types;" 2>/dev/null)
                echo "  $db: total=$count, mutability: $mut"
            else
                echo "  $db: no enum_types table"
            fi
        fi
    fi
done

# ============================================================
# SUMMARY
# ============================================================
hr
echo -e "${CYAN}  PRE-CHECK COMPLETE${NC}"
echo -e "${CYAN}  Copy this entire output to AI for next steps${NC}"
hr
