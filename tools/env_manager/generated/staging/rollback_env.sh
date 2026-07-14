#!/bin/bash
# rollback_env.sh - 环境回滚
#
# 用法: sudo bash rollback_env.sh --env=<env_name> --to=<version>
#
# 流程:
#   1. 停当前 4 服务
#   2. 切 current symlink -> <version>
#   3. 启 4 服务
#   4. 跑 health_check

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/env_common.sh"

ENV_NAME=""
ROLLBACK_TO=""
for arg in "$@"; do
    case "$arg" in
        --env=*)    ENV_NAME="${arg#*=}" ;;
        --to=*)     ROLLBACK_TO="${arg#*=}" ;;
    esac
done

if [ -z "$ENV_NAME" ] || [ -z "$ROLLBACK_TO" ]; then
    echo "用法: sudo bash $0 --env=<env_name> --to=<version>"
    exit 1
fi

load_env_config "$ENV_NAME" || exit 1
ensure_root

echo "==============================================================="
echo "回滚环境: $ENV_NAME"
echo "回滚到:   $ROLLBACK_TO"
echo "==============================================================="

# 1. 校验目标版本存在
if [ ! -d "${ENV_DEPLOY_DIR}/${ROLLBACK_TO}" ]; then
    log_error "版本不存在: ${ENV_DEPLOY_DIR}/${ROLLBACK_TO}"
    exit 1
fi

# 2. 停服务
log_info "[1] 停当前 4 服务"
bash "${SCRIPT_DIR}/stop_env.sh" --env="$ENV_NAME"

# 3. 切 symlink
log_info "[2] 切 current -> $ROLLBACK_TO"
ln -sfn "${ENV_DEPLOY_DIR}/${ROLLBACK_TO}" "$ENV_DEPLOY_CURRENT"

# 4. 修复 db symlink (版本目录内的 architecture.db 可能是文件)
log_info "[3] 修复 db symlink"
ensure_db_symlink

# 5. 启动
log_info "[4] 启动 4 服务"
DEPLOY_VERSION="$ROLLBACK_TO" bash "${SCRIPT_DIR}/start_env.sh" --env="$ENV_NAME"

# 6. 验证
log_info "[5] 跑 health_check"
bash "${SCRIPT_DIR}/health_check.sh" --env="$ENV_NAME"

echo ""
echo "==============================================================="
echo "回滚完成: $ENV_NAME -> $ROLLBACK_TO"
echo "==============================================================="