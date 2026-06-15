# httpClient Context

> **目标文件**: [src/utils/httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js)
> **版本**: 0.1.0 (2026-06-13)
> **维护者**: AI 自动生成 + 人工 review
> **测试覆盖**: ⚠️ **0%**(本 Spec 的 P0 落地点)

---

## 1. 职责 (What)

`httpClient.js` 是项目**所有 HTTP 请求的统一入口**,基于浏览器原生 `fetch` 封装,提供以下核心能力:

- 统一的请求/响应格式(`{ success, data, message, code, httpStatus, traceId }`)
- 401 状态码自动拦截(触发 `onUnauthorized` 回调)
- GET 请求去重(防止并发相同请求)
- 慢请求日志(>1s 自动 `console.warn`)
- AbortSignal 与 timeout 支持
- 统一注入 `trace_id`(用于服务端关联审计日志)
- 统一 `credentials: 'include'`(支持 cookie 鉴权)
- 业务字段映射(`data.data` → `data`,`data.message` → `message`)

**架构位置**:
- 层级: 底层 util
- 上游: `src/utils/api.js`、`src/services/*`、`src/components/*`
- 下游: 浏览器原生 `fetch`

## 2. 关键函数/方法/事件

### 2.1 公共 API

| 函数 | 签名 | 用途 |
|------|------|------|
| `request` | `(method, baseUrl, path, options?) => Promise<Response>` | **主入口**,所有 HTTP 请求通过此函数 |
| `apiV1` | `{ get, post, put, delete, ... }` | 便捷方法,默认 baseUrl = `/api/v1` |
| `apiV2` | `{ get, post, put, delete, ... }` | 便捷方法,默认 baseUrl = `/api/v2` |

### 2.2 内部辅助(项目内可能直接调用)

| 函数 | 签名 | 用途 |
|------|------|------|
| `buildUrlWithParams` | `(baseUrl, path, params) => string` | 处理 URL 拼接 + params 序列化 |
| `inflightCache` | `Map<string, Promise>` | GET 请求去重 |
| `generateTraceId` | `() => string` | `crypto.randomUUID()` |
| `requestIntercept` | `(response) => Response` | 业务字段映射 |

### 2.3 常量

| 常量 | 值 | 用途 |
|------|-----|------|
| `SLOW_REQUEST_THRESHOLD` | `1000` ms | 慢请求阈值 |
| `ErrorCode` | enum | 统一错误码 |

## 3. 调用方 (Callers)

> **实施时通过源码扫描确认**:
> ```bash
> grep -r "from.*httpClient" src/ --include="*.js" --include="*.vue" -l
> grep -r "from.*api" src/utils/ --include="*.js" -l
> ```

**预期调用方清单**(实施时源码扫描确认):

| 文件 | 调用方式 | 备注 |
|------|---------|------|
| `src/utils/api.js` | `import { request } from './httpClient'` | 封装 apiV1/apiV2 |
| `src/services/permissionService.js` | `apiV1.get('/permission-rules', ...)` | 权限规则 |
| `src/services/filterVariant.js` | `apiV2.post('/bo/filter-variant')` | 筛选变体 |
| `src/services/annotation.js` | `apiV1.*` | 批注服务 |
| `src/services/dataModel.js` | `apiV1.*` | 数据模型 |
| `src/services/erDiagram.js` | `apiV1.*` | ER 图 |
| `src/services/fieldMapping.js` | `apiV1.*` | 字段映射 |
| `src/services/dashboard.js` | `apiV1.*` | 仪表板 |
| `src/services/user.js` | `apiV1.*` | 用户 |
| `src/services/audit.js` | `apiV1.*` | 审计 |

**调用方统计**(待源码扫描确认):
- 服务的调用: 预期 ≥ 10 处
- 组件的调用: 预期 ≥ 5 处

## 4. 测试覆盖现状

> **2026-06-13 复核**: 已存在 3 个测试文件覆盖了部分场景,本节为修正版。

| 维度 | 现状 | 文件 / 备注 |
|------|------|-------------|
| 单元测试(Vitest) | 🟡 **部分覆盖** | 3 个现有文件 + 1 个补充文件(本 Spec 落地) |
| MSW 集成 | [X] **未启用** | 项目惯例使用 `vi.mock` 而非 MSW(见 § 6.易错点) |
| E2E(Playwright) | [OK] 间接验证 | 通过 service 层 |
| 覆盖率估算 | **~50%**(参数+去重路径已覆盖) | 待 `npm run test:coverage` 精确测量 |

### 4.1 现有测试文件清单

| 文件 | 行数 | 用例数 | 覆盖场景(对应 OUTPUT_SPEC § 2.1) |
|------|-----|-------|-----------------------------------|
| `src/utils/__tests__/httpClient.params.spec.js` | 224 | 15 | 场景 10(params 基本类型)、11(数组展开)、12(null/undefined 跳过)、中文编码、对象 JSON 化 |
| `src/utils/__tests__/httpClient.dedupe.spec.js` | 181 | 9 | 场景 6(GET 并发去重)、blob/download 不去重、signal 不去重、失败清理、GC |
| `src/utils/__tests__/httpClient-inflight-gc.spec.js` | 47 | 4 | inflightCache GC 计数(`getInflightCount`、`getInflightEvictedCount`) |
| `src/utils/__tests__/httpClient.misc.spec.js` | (本 Spec 新增) | ~10 | 场景 1(200)、2(401)、3(500)、4(网络错误)、5(超时)、8(FormData)、7(慢请求日志) |

### 4.2 覆盖率 gap 分析

| 场景 | 是否已覆盖 | 优先级 | 落地方式 |
|------|----------|-------|---------|
| 1. 200 成功路径 | 🟡 部分(params 测试中含) | 中 | 补充 `httpClient.misc.spec.js` |
| 2. 401 → onUnauthorized | [X] 未覆盖 | **高** | 补充 `httpClient.misc.spec.js` |
| 3. 500 服务器错误 | [X] 未覆盖 | **高** | 补充 `httpClient.misc.spec.js` |
| 4. 网络错误 | 🟡 部分(dedupe 测试中含 TypeError) | 中 | 补充 `httpClient.misc.spec.js` |
| 5. 超时 | [X] 未覆盖 | **高** | 补充 `httpClient.misc.spec.js` |
| 6. GET 并发去重 | [OK] 已覆盖 | - | - |
| 7. 慢请求日志 | [X] 未覆盖 | 中 | 补充 `httpClient.misc.spec.js` |
| 8. FormData body | [X] 未覆盖 | 中 | 补充 `httpClient.misc.spec.js` |
| 9. AbortSignal 主动取消 | [X] 未覆盖 | 低 | 补充 `httpClient.misc.spec.js` |
| 10. params 基本类型 | [OK] 已覆盖 | - | - |
| 11. params 数组 | [OK] 已覆盖 | - | - |
| 12. null/undefined 跳过 | [OK] 已覆盖 | - | - |

**目标**: ≥ 80% 覆盖率,**关键函数 100%**(`request`、`buildUrlWithParams`、`inflightCache`)
**当前**: ~50% → 补充完成后预计 ~85%

**测试场景清单**(12 类必覆盖):见 [.trae/skills/test-gen/OUTPUT_SPEC.md § 2.1](file:///d:/filework/excel-to-diagram/.trae/skills/test-gen/OUTPUT_SPEC.md)

## 5. 边界场景 (Edge Cases)

| 场景 | 当前处理 | 已知问题 |
|------|----------|----------|
| 空 body | 默认空对象 | 无 |
| 超大 body(>10MB) | 未限制 | ⚠️ 风险 |
| GET 参数含特殊字符 | URLSearchParams 编码 | 无 |
| 数组 params | `?k=1&k=2` 展开 | [OK] 已修复(2026-06-08) |
| 并发相同 GET 请求 | inflightCache 去重 | 无 |
| 超时 | AbortController + timeout | 无 |
| 401 响应 | 触发 onUnauthorized | 无 |
| 500 响应 | 返回 SERVER_ERROR | 无 |
| 网络断开 | 返回 NETWORK_ERROR | 无 |
| FormData body | Content-Type 自动移除 | 无 |
| AbortSignal 主动取消 | 立即终止 | 无 |
| null/undefined params | 跳过 | [OK] 已修复 |

## 6. 易错点 (Gotchas)

- [OK] **使用前必读**: `request(method, baseUrl, path, options?)` 必须传 `baseUrl`
- [OK] **优先用 apiV1/apiV2**: 不要直接调 `request()`,除非特殊场景
- [OK] **GET 请求自动去重**: 利用 `inflightCache`,不要手动 dedup
- [X] **不要直接使用 fetch**: 应统一调用 `request()` 或 `apiV1/apiV2`
- [X] **不要在 component 内新建 httpClient 实例**: util 是单例
- ⚠️ **params 数组**: 必须 `?k=1&k=2`(FIX-2026-06-08 后),不要 `?k[]=1`
- ⚠️ **FormData**: 不要手动设置 Content-Type,让浏览器自动设置
- ⚠️ **401 处理**: 调用方必须提供 `onUnauthorized` 回调,否则不处理
- ⚠️ **cookie 鉴权**: `credentials: 'include'` 默认开启,跨域需后端 CORS 允许

## 7. 变更历史 (Changelog)

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.1 | 2026-06-13 | **复核**: 测试覆盖从"0%"修正为"~50%(部分覆盖)",新增 § 4.1/4.2 gap 分析 | AI |
| 0.1.0 | 2026-06-13 | 初版 Context 文档(实施扫描后更新) | AI |
| (源文件) | 2026-06-08 | params 数组序列化修复 | - |
| (源文件) | 2026-06-02 | inflightCache 引入 GET 去重 | - |

---

## 8. 相关链接

- [源文件 httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js)
- [Skill test-gen SKILL.md](file:///d:/filework/excel-to-diagram/.trae/skills/test-gen/SKILL.md)
- [Skill test-gen OUTPUT_SPEC.md § 2.1](file:///d:/filework/excel-to-diagram/.trae/skills/test-gen/OUTPUT_SPEC.md)
- [.trae/rules/frontend-testing-standards.md](file:///d:/filework/excel-to-diagram/.trae/rules/frontend-testing-standards.md)