#!/bin/bash
# env_manager.sh - 环境管理入口 (V007.50 2026-07-14)
#
# 用法:
#   sudo bash env_manager.sh render --env=<env_name>     # 渲染生成所有脚本到 generated/<env>/
#   sudo bash env_manager.sh list                        # 列出所有环境
#   sudo bash env_manager.sh validate                    # 校验 environments.yaml schema
#   sudo bash env_manager.sh diff --env=staging          # 比较生成的脚本与现有 staging 脚本
#
# 设计:
#   1. 读 environments.yaml
#   2. 用模板 (templates/*.sh) 渲染生成 generated/<env>/<script>
#   3. 复制到 远端 /opt/app/<env>/scripts/

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="${SCRIPT_DIR}/templates"
GENERATED_DIR="${SCRIPT_DIR}/generated"
mkdir -p "$GENERATED_DIR"

source "${SCRIPT_DIR}/lib/env_common.sh"

CMD=""
ENV_NAME=""
for arg in "$@"; do
    case "$arg" in
        render|list|validate|diff) CMD="$arg" ;;
        --env=*) ENV_NAME="${arg#*=}" ;;
        *) echo "[WARN] unknown arg: $arg" ;;
    esac
done

case "$CMD" in
    list)
        echo "可用环境:"
        # 只在 environments: 块下查找 2 空格缩进的顶层 key
        awk '/^environments:$/{in_env=1; next} in_env && /^  [a-z]+:$/{gsub(/:$/,""); print "  - " $1} /^common:$/{exit}' "$ENVIRONMENTS_FILE"
        ;;
    validate)
        echo "校验 environments.yaml ..."
        for env in $(awk '/^environments:$/{in_env=1; next} in_env && /^  [a-z]+:$/{gsub(/:$/,""); print $1} /^common:$/{exit}' "$ENVIRONMENTS_FILE"); do
            load_env_config "$env"
            echo "  [OK] $env: root=$ENV_ROOT backend=$ENV_BACKEND_PORT unified=$ENV_UNIFIED_PORT log=$ENV_LOG_PORT core=$ENV_CORE_PORT"
        done
        ;;
    render)
        if [ -z "$ENV_NAME" ]; then
            echo "用法: sudo bash $0 render --env=<env_name>"
            exit 1
        fi
        load_env_config "$ENV_NAME" || exit 1

        OUT_DIR="${GENERATED_DIR}/${ENV_NAME}"
        mkdir -p "$OUT_DIR"

        for tmpl in start_env.sh stop_env.sh health_check.sh e2e_test.sh rollback_env.sh; do
            log_info "render: $tmpl"
            cp "${TEMPLATES_DIR}/$tmpl" "${OUT_DIR}/$tmpl"
            chmod +x "${OUT_DIR}/$tmpl"
        done

        # 同时复制 lib/ (脚本 source ${SCRIPT_DIR}/lib/env_common.sh)
        log_info "render: lib/env_common.sh"
        cp -r "${ENV_MANAGER_DIR}/lib" "${OUT_DIR}/lib"

        # 同时复制 environments.yaml (脚本需要)
        log_info "render: environments.yaml"
        cp "${ENVIRONMENTS_FILE}" "${OUT_DIR}/environments.yaml"

        log_ok "生成完成: $OUT_DIR"
        echo ""
        echo "生成的文件:"
        ls -la "$OUT_DIR"
        echo ""
        echo "下一步:"
        echo "  1. 上传到远端: scp $OUT_DIR/*.sh root@172.20.59.7:/opt/app/${ENV_NAME}/scripts/"
        echo "  2. 跑健康检查: bash ${OUT_DIR}/health_check.sh --env=$ENV_NAME"
        ;;
    diff)
        if [ -z "$ENV_NAME" ]; then
            echo "用法: sudo bash $0 diff --env=<env_name>"
            exit 1
        fi
        load_env_config "$ENV_NAME" || exit 1
        OUT_DIR="${GENERATED_DIR}/${ENV_NAME}"

        echo "==============================================================="
        echo "对比生成的脚本 vs 现有 $ENV_NAME 脚本"
        echo "==============================================================="

        # 对比点 1: 端口
        log_info "[1] 端口对比"
        echo "  生成: backend=$ENV_BACKEND_PORT unified=$ENV_UNIFIED_PORT log=$ENV_LOG_PORT core=$ENV_CORE_PORT"
        if [ -f "${ENV_ROOT}/scripts/start_staging.sh" ]; then
            log_info "  现有: $(grep -E 'PORT=' ${ENV_ROOT}/scripts/start_staging.sh | head -4)"
        fi

        # 对比点 2: 路径
        log_info "[2] 路径对比"
        echo "  生成 root: $ENV_ROOT"
        echo "  生成 db:   $ENV_DB"

        # 对比点 3: 关键脚本存在性
        log_info "[3] 关键脚本存在性"
        for s in start_staging.sh stop_staging.sh staging_e2e_test.sh staging_health_check.sh; do
            if [ -f "${ENV_ROOT}/scripts/$s" ]; then
                echo "  现有: $s (size=$(stat -c %s ${ENV_ROOT}/scripts/$s))"
            else
                echo "  现有: $s MISSING"
            fi
        done
        ;;
    *)
        echo "用法: sudo bash $0 {render|list|validate|diff} [--env=<env_name>]"
        echo ""
        echo "命令:"
        echo "  list      列出所有环境"
        echo "  validate  校验 environments.yaml"
        echo "  render    生成指定环境的所有脚本"
        echo "  diff      对比生成的脚本与现有脚本"
        ;;
esac