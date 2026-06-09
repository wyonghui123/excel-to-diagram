---
title: API 接口参考
version: 1.0.0
date: 2026-06-07
status: 活跃
audience: 开发者
---

# API 接口文档

## 1. 概述

本项目提供两类 API：
1. **AI 代理 API**：用于调用 DeepSeek / 智谱AI 等大模型服务
2. **Cloudflare Workers API**：无服务器函数，处理 API 请求转发

---

## 2. AI 代理 API

### 2.1 DeepSeek API

**端点**: `/api/deepseek`

**请求方法**: `POST`

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
  "messages": [
    { "role": "system", "content": "你是一个架构助手" },
    { "role": "user", "content": "解释微服务架构" }
  ],
  "model": "deepseek-chat"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| messages | Array | 是 | 对话消息数组 |
| model | string | 否 | 模型名称，默认 `deepseek-chat` |

**响应示例**:
```json
{
  "id": "gen-123456",
  "object": "chat.completion",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "微服务架构是一种..."
    }
  }]
}
```

**错误响应**:
```json
{
  "error": "错误信息"
}
```

---

### 2.2 智谱 AI API

**端点**: `/api/zhipu`

**请求方法**: `POST`

**请求体**:
```json
{
  "messages": [
    { "role": "user", "content": "请生成架构图代码" }
  ],
  "model": "glm-4"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| messages | Array | 是 | 对话消息数组 |
| model | string | 否 | 模型名称，默认 `glm-4` |

**错误码**:

| code | 说明 |
|------|------|
| 10001 | 系统错误 |
| 20003 | Token 无效 |
| 40002 | 请求参数无效 |
| 80001 | 安全过滤 |

---

## 3. Cloudflare Workers API

### 3.1 Workers 代理端点

**端点**: `https://excel-to-diagram.workers.dev/api/*`

所有请求会转发到对应的 AI 服务，保护 API Key 不暴露在客户端。

### 3.2 请求格式

```javascript
// 客户端调用示例
const response = await fetch('https://excel-to-diagram.workers.dev/api/deepseek', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    messages: [{ role: 'user', content: 'Hello' }]
  })
})
```

---

## 4. 环境变量

### 4.1 Vercel 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 是 |
| `ZHIPU_API_KEY` | 智谱AI API 密钥 | 是 |
| `VITE_API_BASE_URL` | API 基础路径 | 否 |

### 4.2 Cloudflare Workers 密钥

在 Cloudflare Dashboard → Workers & Pages → Settings → Variables 中配置：

| 变量名 | 说明 |
|--------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `ZHIPU_API_KEY` | 智谱 AI Key |

---

## 5. API 限流

| 端点 | 限制 |
|------|------|
| DeepSeek API | 60 请求/分钟 |
| 智谱 AI API | 100 请求/分钟 |
| Cloudflare Workers | 100,000 请求/天 |

---

## 6. 错误处理

所有 API 错误遵循统一格式：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "错误描述",
    "details": {}
  }
}
```

### 通用错误码

| code | HTTP status | 说明 |
|------|-------------|------|
| `METHOD_NOT_ALLOWED` | 405 | 仅支持 POST |
| `UNAUTHORIZED` | 401 | 认证失败 |
| `RATE_LIMITED` | 429 | 请求过于频繁 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

---

## 7. 使用示例

### 7.1 前端调用

```javascript
// 调用 DeepSeek API
const response = await fetch('/api/deepseek', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    messages: [
      { role: 'user', content: '帮我解释什么是微服务' }
    ]
  })
})

const data = await response.json()
console.log(data.choices[0].message.content)
```

### 7.2 Node.js 调用

```javascript
const response = await fetch('https://excel-to-diagram.workers.dev/api/deepseek', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    messages: [{ role: 'user', content: 'Hello' }]
  })
})
```

---

*文档更新时间: 2026-04-08*
