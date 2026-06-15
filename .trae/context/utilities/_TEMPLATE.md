# utilities Context 模板

> **本文件为 `utilities/` 目录专用模板,在通用模板基础上聚焦 util 函数特性。**
> **适用范围**: `.trae/context/utilities/<name>.md`,描述 `src/utils/<name>.js` 等纯函数/工具模块。

## 与通用模板的差异

| 维度 | 通用 | utilities |
|------|------|-----------|
| 调用方范围 | 项目全部 | 项目全部,但更关注"被谁用" |
| 边界场景 | 通用边界 | 输入参数边界为主 |
| 测试覆盖 | 单元 / 集成 / E2E | **单元测试为主**(util 通常是纯函数) |
| 易错点 | 通用陷阱 | 函数副作用 / 性能 / 副作用顺序 |

---

# <util-name> Context

## 1. 职责 (What)

> 用 1-2 段说明该 util 的核心职责。

**示例**:
> `<util-name>` 是项目统一的 HTTP 客户端,封装 fetch,提供统一的:
> - 响应格式 `{ success, data, message, code, httpStatus, traceId }`
> - 401 自动拦截
> - 慢请求日志(>1s)
> - GET 请求去重

**架构位置**:
- 层级: 底层 util
- 上游: 直接被 service / component 调用
- 下游: 浏览器原生 `fetch`

## 2. 关键函数/方法/事件

### 2.1 公共 API

| 函数 | 签名 | 用途 |
|------|------|------|
| `request` | `(method, baseUrl, path, options?) => Promise<Response>` | 主入口 |
| `<helper1>` | `(...args) => <ret>` | <用途> |
| `<helper2>` | `(...args) => <ret>` | <用途> |

### 2.2 内部辅助

| 函数 | 签名 | 用途 |
|------|------|------|
| `inflightCache` | `Map<key, Promise>` | GET 请求去重 |
| `generateTraceId` | `() => string` | crypto.randomUUID |

## 3. 调用方 (Callers)

> 通过 `grep -r "import.*<util-name>" src/` 自动扫描。

| 文件 | 调用方式 | 频次 |
|------|---------|------|
| `src/services/<service>.js` | `import { request } from '<util>'` | N |
| `src/components/<component>.vue` | `import { request } from '<util>'` | N |

**调用方统计**:
- 服务的调用: <N> 处
- 组件的调用: <N> 处
- 总调用: <N> 处

## 4. 测试覆盖现状

| 维度 | 现状 | 文件 / 备注 |
|------|------|-------------|
| 单元测试(Vitest) | ⚠️ 0% | 待 Skill test-gen 生成 |
| MSW 集成 | ⚠️ 0% | 待 Skill test-gen 生成 |
| E2E(Playwright) | [OK] 间接验证 | 通过 service 层 |
| 覆盖率 | 0% | - |

**目标**: ≥ 80% 覆盖率,关键函数 100%

## 5. 边界场景 (Edge Cases)

| 场景 | 当前处理 | 测试覆盖 |
|------|----------|----------|
| 空 body | 默认空对象 | [X] |
| 超大 body(>10MB) | 未限制 | [X] |
| GET 参数含特殊字符 | URLSearchParams 编码 | [X] |
| 并发相同 GET 请求 | inflightCache 去重 | [X] |
| 超时 | AbortController + timeout | [X] |
| 401 响应 | 触发 onUnauthorized | [X] |
| 500 响应 | 返回 SERVER_ERROR | [X] |
| 网络断开 | 返回 NETWORK_ERROR | [X] |

## 6. 易错点 (Gotchas)

- [OK] **使用前必读**: 必须传 `baseUrl` 参数,不能省略
- [OK] **GET 请求自动去重**: 不要手动 mock,利用 `inflightCache`
- [X] **不要直接使用 fetch**: 应统一调用 `request()`
- [X] **不要在 component 内新建 httpClient 实例**: 通过 util 单例
- ⚠️ **params 数组**: 必须用 `?k=1&k=2`,不要用 `?k[]=1`
- ⚠️ **FormData**: 不要手动设置 Content-Type
- ⚠️ **401 处理**: 必须在调用方提供 `onUnauthorized` 回调

## 7. 变更历史 (Changelog)

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | YYYY-MM-DD | 初版 | AI |