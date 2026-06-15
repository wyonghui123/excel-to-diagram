# 任务: 遍历 /api/v1/* 端点, 批量迁移到 v2 (Agent 协作版)

> **目标**: 把所有 v1 端点的 `V1_TO_V2_PATH_MAP` 补齐, 让 v1→v2 自动迁移覆盖完整
> **参考**: Agent 之前已迁移了 `user-groups` (复数) → `user_group` (单数), 现在要批量扩展

## 背景 (重要)

之前的 Agent 已经做了以下改进:
- 路径准确: `/api/v1/user-groups` → `/api/v2/bo/user_group` (单数)
- 支持子路径: `/api/v1/user-groups/1` → `/api/v2/bo/user_group/1`
- 新增 `migrated_to` 字段 (供客户端编程访问)
- 可扩展: 未来有新映射只需在 `V1_TO_V2_PATH_MAP` 加一行

**现在需要扩展覆盖更多 v1 端点**, 避免前端/客户端调用 v1 时出现 500/404 而非 410。

## 任务清单

### 1. 列出所有 v1 端点 (发现)

```bash
# 在 d:\filework\excel-to-diagram 目录下
# 查找所有 v1 API 注册点
grep -r "url_prefix.*/api/v1" meta/ --include="*.py" -l
grep -r "@.*\.route.*['\"]/" meta/api/ --include="*.py" | grep -v v2 | head -50
```

### 2. 收集候选 v1 路径

预期需要迁移的 v1 端点族 (从代码扫描获取完整列表):
- `/api/v1/users` → ?
- `/api/v1/roles` → ?
- `/api/v1/permissions` → ?
- `/api/v1/permission-bundles` → ?
- `/api/v1/products` → ?
- `/api/v1/domains` → ?
- `/api/v1/business-objects` → ?
- `/api/v1/associations` → ?
- `/api/v1/menus` → ?
- `/api/v1/relationships` → ?
- ... (实际列表以代码扫描为准)

### 3. 对每个 v1 端点, 找到对应的 v2 端点

参考依据:
- `meta/api/` 目录下的 Blueprint 注册 (找 `url_prefix='/api/v2/...'`)
- v2 端点通常在 `/api/v2/bo/<singular_name>` (单数)
- 详细查看每个 blueprint 的实际路径

### 4. 找到 `V1_TO_V2_PATH_MAP` 的代码位置

```bash
grep -r "V1_TO_V2_PATH_MAP" meta/ --include="*.py" -l
```

可能位置: `meta/core/app_builder.py` 的 `V1_SPECIAL_PREFIXES` 附近, 或者专门的兼容层。

### 5. 批量添加映射

对每个找到的 v1 → v2 映射, 在 `V1_TO_V2_PATH_MAP` 中加一行 (格式参考 user-groups 的写法)。

### 6. 验证

启动服务, 用 curl 测试:

```bash
# 测试每个迁移路径
for url in /api/v1/users /api/v1/roles /api/v1/products; do
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3010$url)
  echo "$url -> $status (期望 410)"
done

# 验证 migrated_to 字段
curl -s http://localhost:3010/api/v1/users | python -m json.tool
```

## 验收标准 (DoD)

1. ✅ 至少发现并迁移 **20+ 个 v1 端点** 到 v2
2. ✅ 所有 v1 端点返回 **410** (而非 404/500)
3. ✅ 所有 410 响应包含 **`migrated_to` 字段** 指向正确 v2 端点
4. ✅ 子路径迁移正确 (`/api/v1/users/1` → `/api/v2/bo/user/1`)
5. ✅ 不破坏现有 v1/v2 业务功能 (跑 E2E 验证)

## 建议执行顺序

1. **扫描阶段 (15min)**: 列出所有 v1 端点 + 找到 v2 对应
2. **编写映射 (20min)**: 在 `V1_TO_V2_PATH_MAP` 加 20+ 行
3. **本地验证 (10min)**: curl 测试每个端点
4. **E2E 验证 (15min)**: 跑 `python d:\filework\test.py --file e2e/features/...` 相关测试
5. **报告 (5min)**: 列出已迁移端点 + 任何无法迁移的项

## 注意事项

- ⚠️ 某些 v1 端点可能没有 v2 对应 (旧功能已废弃), 这些保持 410 但不指向 v2
- ⚠️ 注意单复数 (user vs users, role vs roles)
- ⚠️ 注意下划线 vs 中划线 (user_group vs user-group)
- ⚠️ 子路径: `/api/v1/X/{id}/Y/{id}` 也需要正确映射
- ⚠️ HTTP method 必须保留: GET/POST/PUT/DELETE/PATCH 都要支持

## 相关文件路径

- 兼容层: `meta/core/app_builder.py` (找 `V1_SPECIAL_PREFIXES` / `V1_TO_V2_PATH_MAP`)
- v1 blueprints: `meta/api/*.py` 中 `Blueprint('xxx', url_prefix='/api/v1/...')`
- v2 blueprints: `meta/api/*.py` 中 `Blueprint('xxx', url_prefix='/api/v2/...')`
- E2E 测试: `e2e/features/` 和 `e2e/business-flow/`

## 报告格式

完成后请用以下格式汇报:

```
## 已迁移端点清单

| v1 路径 | v2 路径 | HTTP methods |
|---------|---------|--------------|
| /api/v1/users | /api/v2/bo/user | GET, POST, PUT, DELETE |
| /api/v1/roles | /api/v2/bo/role | GET, POST, PUT, DELETE |
| ... | ... | ... |

## 验证结果
- 总数: X
- 410 响应: X (期望 X)
- migrated_to 字段: 100% 覆盖
- E2E 回归: PASS/FAIL

## 任何未迁移项
- (列出 v1 端点 + 未迁移原因)
```
