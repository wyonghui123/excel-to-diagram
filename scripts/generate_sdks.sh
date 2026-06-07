#!/bin/bash
# D-4: 客户端 SDK 自动生成 (openapi-generator)
# 输出: sdk/{python,javascript,typescript}
set -e

BASE_URL="${1:-http://localhost:3010}"
OUTPUT_BASE="$(cd "$(dirname "$0")/.." && pwd)/sdk"
mkdir -p "$OUTPUT_BASE"

echo "[generate_sdks] Fetching OpenAPI from $BASE_URL/api/v2/action/_openapi.json"
curl -s "$BASE_URL/api/v2/action/_openapi.json" -o "$OUTPUT_BASE/openapi.json"
echo "[generate_sdks] ✅ Saved $OUTPUT_BASE/openapi.json"

# 检查 openapi-generator-cli 是否可用
if ! command -v openapi-generator-cli &> /dev/null; then
    if ! npx --no-install openapi-generator-cli --version &> /dev/null 2>&1; then
        echo "[generate_sdks] ⚠️ openapi-generator-cli 未安装"
        echo "[generate_sdks] 安装方法:"
        echo "  npm install -g @openapitools/openapi-generator-cli"
        echo "  # 或"
        echo "  brew install openapi-generator"
        echo "  # 或"
        echo "  npx @openapitools/openapi-generator-cli generate -i openapi.json -g python -o sdk/python"
        echo ""
        echo "[generate_sdks] 跳过 SDK 生成, 仅保留 openapi.json"
        exit 0
    fi
    GEN_CMD="npx --no-install openapi-generator-cli"
else
    GEN_CMD="openapi-generator-cli"
fi

# 生成 3 种语言 SDK
for lang in python javascript typescript-fetch; do
    out_dir="$OUTPUT_BASE/${lang}"
    echo "[generate_sdks] Generating $lang SDK -> $out_dir"
    $GEN_CMD generate \
        -i "$OUTPUT_BASE/openapi.json" \
        -g "$lang" \
        -o "$out_dir" \
        --additional-properties=packageName=bo_action_client,projectName=bo-action-client \
        2>&1 | tail -5
done

echo "[generate_sdks] ✅ All SDKs generated in $OUTPUT_BASE"
echo "[generate_sdks] 使用方法:"
echo "  cd sdk/python && pip install ."
echo "  from bo_action_client import ApiClient, Configuration"
echo "  # ... (见 openapi-generator 文档)"
