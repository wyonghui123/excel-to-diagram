# test-gen 输出规范 (OUTPUT_SPEC)

> **版本**: v0.1.0 (2026-06-13)
> **配套**: [SKILL.md](./SKILL.md)、[PROMPT_TEMPLATE.md](./PROMPT_TEMPLATE.md)
> **目的**: 定义 test-gen Skill 生成代码的详细规范,保证 Agent 输出稳定

---

## 1. 输出文件结构

```
src/
├── utils/
│   ├── httpClient.js          (源文件, 不变)
│   └── httpClient.spec.js     (新增, 测试文件)
├── mocks/
│   └── handlers.js            (新增或更新, MSW handler)
└── ...
.trae/
└── state/
    └── agent-runs.jsonl       (追加, 可观测性)
```

---

## 2. JS Util 测试规范

### 2.1 必须覆盖的 12 类场景

#### 场景 1: 200 成功路径
```javascript
it('[OK] returns success on 200', async () => {
  server.use(http.get('/api/test', () => HttpResponse.json({ data: 'ok' })));
  const result = await request('GET', 'http://localhost', '/api/test');
  expect(result.success).toBe(true);
  expect(result.data).toEqual({ data: 'ok' });
});
```

#### 场景 2: 401 触发 onUnauthorized
```javascript
it('[OK] triggers onUnauthorized on 401', async () => {
  const onUnauth = vi.fn();
  server.use(http.get('/api/test', () => new HttpResponse(null, { status: 401 })));
  await request('GET', 'http://localhost', '/api/test', { onUnauthorized: onUnauth });
  expect(onUnauth).toHaveBeenCalled();
});
```

#### 场景 3: 500 服务器错误
```javascript
it('[OK] returns SERVER_ERROR on 500', async () => {
  server.use(http.get('/api/test', () => new HttpResponse(null, { status: 500 })));
  const result = await request('GET', 'http://localhost', '/api/test');
  expect(result.success).toBe(false);
  expect(result.code).toBe('SERVER_ERROR');
});
```

#### 场景 4: 网络错误
```javascript
it('[OK] returns NETWORK_ERROR on fetch reject', async () => {
  server.use(http.get('/api/test', () => HttpResponse.error()));
  const result = await request('GET', 'http://localhost', '/api/test');
  expect(result.success).toBe(false);
  expect(result.code).toBe('NETWORK_ERROR');
});
```

#### 场景 5: 超时
```javascript
it('[OK] returns TIMEOUT on abort', async () => {
  server.use(http.get('/api/test', async () => {
    await new Promise(r => setTimeout(r, 10000));
    return HttpResponse.json({});
  }));
  const result = await request('GET', 'http://localhost', '/api/test', { timeout: 100 });
  expect(result.success).toBe(false);
  expect(result.code).toBe('TIMEOUT');
});
```

#### 场景 6: GET 请求去重
```javascript
it('[OK] dedups concurrent GET requests', async () => {
  let callCount = 0;
  server.use(http.get('/api/test', () => {
    callCount++;
    return HttpResponse.json({ data: callCount });
  }));
  const [r1, r2] = await Promise.all([
    request('GET', 'http://localhost', '/api/test'),
    request('GET', 'http://localhost', '/api/test'),
  ]);
  expect(callCount).toBe(1);
  expect(r1).toEqual(r2);
});
```

#### 场景 7: 慢请求日志
```javascript
it('[OK] logs slow requests >1s', async () => {
  const logSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  server.use(http.get('/api/test', async () => {
    await new Promise(r => setTimeout(r, 1100));
    return HttpResponse.json({});
  }));
  await request('GET', 'http://localhost', '/api/test');
  expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('slow'));
  logSpy.mockRestore();
});
```

#### 场景 8: FormData body
```javascript
it('[OK] handles FormData body (auto remove Content-Type)', async () => {
  const formData = new FormData();
  formData.append('key', 'value');
  server.use(http.post('/api/upload', () => HttpResponse.json({ ok: true })));
  await request('POST', 'http://localhost', '/api/upload', { body: formData });
  // 验证 Content-Type 由浏览器自动设置,不在 headers 中显式设置
});
```

#### 场景 9: AbortSignal
```javascript
it('[OK] respects AbortSignal', async () => {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 50);
  server.use(http.get('/api/test', () => HttpResponse.json({})));
  const result = await request('GET', 'http://localhost', '/api/test', { signal: controller.signal });
  expect(result.success).toBe(false);
});
```

#### 场景 10: params 序列化(基本类型)
```javascript
it('[OK] serializes basic params', async () => {
  server.use(http.get('/api/test', ({ request }) => {
    const url = new URL(request.url);
    expect(url.searchParams.get('a')).toBe('1');
    return HttpResponse.json({});
  }));
  await request('GET', 'http://localhost', '/api/test', { params: { a: 1, b: 'x' } });
});
```

#### 场景 11: params 序列化(数组)
```javascript
it('[OK] serializes array params', async () => {
  server.use(http.get('/api/test', ({ request }) => {
    const url = new URL(request.url);
    expect(url.searchParams.getAll('filter')).toEqual(['18', '19']);
    return HttpResponse.json({});
  }));
  await request('GET', 'http://localhost', '/api/test', { params: { filter: [18, 19] } });
});
```

#### 场景 12: null/undefined params 跳过
```javascript
it('[OK] skips null/undefined params', async () => {
  server.use(http.get('/api/test', ({ request }) => {
    const url = new URL(request.url);
    expect(url.searchParams.has('a')).toBe(true);
    expect(url.searchParams.has('b')).toBe(false);
    expect(url.searchParams.has('c')).toBe(false);
    return HttpResponse.json({});
  }));
  await request('GET', 'http://localhost', '/api/test', { params: { a: 1, b: null, c: undefined } });
});
```

### 2.2 文件模板

```javascript
// src/utils/<name>.spec.js
import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { <import> } from './<name>';
// import { handlers } from '../../mocks/handlers';  // 视情况

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('<name>.js', () => {
  // 12 类场景的 it() 块
});
```

---

## 3. Vue 组件测试规范

### 3.1 必须覆盖的 5 维度

#### 维度 1: props 默认值 + 类型校验
```javascript
it('[OK] uses default props', () => {
  const wrapper = mount(MyComponent);
  expect(wrapper.props('title')).toBe('Default Title');
});

it('[X] warns on invalid prop type', () => {
  const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  mount(MyComponent, { props: { count: 'invalid' } });
  expect(warnSpy).toHaveBeenCalled();
});
```

#### 维度 2: emit 事件触发
```javascript
it('[OK] emits "change" event', async () => {
  const wrapper = mount(MyComponent);
  await wrapper.find('[data-testid="trigger"]').trigger('click');
  expect(wrapper.emitted('change')).toBeTruthy();
});
```

#### 维度 3: slot 内容渲染
```javascript
it('[OK] renders slot content', () => {
  const wrapper = mount(MyComponent, {
    slots: { default: '<span data-testid="slot-content">Hello</span>' },
  });
  expect(wrapper.find('[data-testid="slot-content"]').exists()).toBe(true);
});
```

#### 维度 4: computed 缓存性
```javascript
it('[OK] computed is cached unless deps change', async () => {
  const wrapper = mount(MyComponent, { props: { value: 1 } });
  const spy = vi.spyOn(wrapper.vm, 'computedProp', 'get');
  // 触发不相关的 reactive 变化
  await wrapper.setProps({ unrelatedProp: 'change' });
  expect(spy).toHaveBeenCalledTimes(1); // 未重复调用
});
```

#### 维度 5: store 依赖(Pinia)
```javascript
it('[OK] works with Pinia store', () => {
  const pinia = createPinia();
  const wrapper = mount(MyComponent, {
    global: { plugins: [pinia] },
  });
  // 测试 store 交互
});
```

### 3.2 文件模板

```javascript
// src/components/<name>.spec.js
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import MyComponent from './MyComponent.vue';

describe('MyComponent.vue', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('[OK] renders', () => {
    const wrapper = mount(MyComponent);
    expect(wrapper.exists()).toBe(true);
  });

  // 5 维度的 it() 块
});
```

---

## 4. MSW Handler 规范

### 4.1 文件位置

`src/mocks/handlers.js`

### 4.2 必须包含的 handler

- 默认成功(200)
- 401(未授权)
- 500(服务器错误)
- 网络错误(`http.get(..., () => HttpResponse.error())`)
- 超时(可选项)

### 4.3 模板

```javascript
// src/mocks/handlers.js
import { http, HttpResponse, delay } from 'msw';

export const handlers = [
  // 默认成功
  http.get('/api/*', async () => {
    await delay(50);
    return HttpResponse.json({ success: true });
  }),

  // 401
  http.post('/api/auth', () => new HttpResponse(null, { status: 401 })),

  // 500
  http.get('/api/error', () => new HttpResponse(null, { status: 500 })),
];
```

---

## 5. agent-runs.jsonl 追加格式

```json
{"requestId":"uuid-xxx","agentId":"agent-A","skillName":"test-gen","startedAt":"2026-06-13T10:00:00Z","finishedAt":"2026-06-13T10:01:23Z","status":"success","files_changed":["src/utils/httpClient.spec.js","src/mocks/handlers.js"],"tokens_used":3420,"coverage":{"lines":85.3,"branches":78.2},"target":"src/utils/httpClient.js"}
```

字段说明:

| 字段 | 必填 | 说明 |
|------|------|------|
| requestId | [OK] | UUID |
| agentId | [OK] | 触发本次 Skill 的 Agent ID |
| skillName | [OK] | "test-gen" |
| startedAt | [OK] | ISO 8601 |
| finishedAt | [X] | 完成后填 |
| status | [OK] | running/success/failed/denied |
| files_changed | [X] | 完成后填 |
| tokens_used | [X] | 完成后填 |
| coverage | [X] | 完成后填 |
| target | [OK] | 目标源文件路径 |

---

## 6. 验证清单

生成代码后必须通过:

- [ ] `vitest run <target>.spec.js` 通过
- [ ] 覆盖率 ≥ 80%(关键函数 100%)
- [ ] `ai_content_guard.py <target>.spec.js` 通过
- [ ] `.trae/state/agent-runs.jsonl` 已追加
- [ ] `.trae/skills/INDEX.md` 中 test-gen 的 last_updated 已更新

---

## 7. 版本历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |