---
description: Trae IDE 沙箱 v2 配置指南 - 涉及 sandbox.json 自定义、网络控制、白名单、高风险命令拦截时加载。封装沙箱 5 大机制 + 与项目白名单机制的关系。
globs: ["**/.trae-cn/sandbox.json", "**/sandbox.json"]
version: "0.1.0"
author: "AI"
last_updated: "2026-09-02"
---

# Trae IDE 沙箱 v2 配置指南 (v5.4)

> **官方文档**：[docs.trae.cn/ide/sandbox](https://docs.trae.cn/ide/sandbox)
> **状态**：v5.4 新增特性，已支持自定义 sandbox.json

---

## 1. 沙箱定位

> **沙箱为智能体生成的命令提供受限的执行环境**，确保智能体在安全隔离的环境中运行命令，防止未经授权的文件访问。

---

## 2. sandbox.json 配置文件

### 2.1 位置

| 操作系统 | 路径 |
|---------|------|
| **Windows** | `%USERPROFILE%\.trae-cn\sandbox.json` |
| **macOS / Linux** | `~/.trae-cn/sandbox.json` |

### 2.2 创建步骤

1. 设置 → 对话流
2. 沙箱自定义配置 → 打开配置
3. TRAE 自动创建 sandbox.json 并打开
4. 编辑保存

### 2.3 完整 schema

```json
{
  "filesystem": {
    "readWrite": [
      "D:/projects/myapp/src",
      "~/Documents/work"
    ],
    "readOnly": [
      "C:/Program Files",
      "/usr/local/bin"
    ]
  },
  "network": {
    "default": "allow",
    "allow": [
      "*.github.com:443",
      "[10.0.0.0/8]:22"
    ],
    "deny": [
      "[192.168.0.0/16]",
      "*.internal.corp"
    ]
  }
}
```

---

## 3. 文件系统访问控制

### 3.1 路径格式

- **绝对路径**：`/usr/local/bin` 或 `C:\Program Files`
- **Home 目录**：`~/Documents`
- **环境变量**：`$HOME/.config`
- **工作区变量**：`$WORKSPACE_FOLDER`

### 3.2 平台处理

| OS | Unix 风格 `/usr/lib` | Git Bash `/c/Users` | Windows `C:\Users` |
|----|---------------------|--------------------|--------------------|
| Windows | 自动忽略 | 转换为标准路径 | 接受 |
| macOS / Linux | 接受 | N/A | 自动忽略 |

### 3.3 优先级规则

1. **路径越长越精确，优先级越高**
2. **readOnly > readWrite**（冲突时）
3. **未在列表中的路径**：按系统默认策略（见 §5）

---

## 4. 网络访问控制（仅 Windows）

### 4.1 字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `default` | string | "allow" | allow / deny |
| `allow` | string[] | [] | 允许列表 |
| `deny` | string[] | [] | 禁止列表 |

### 4.2 地址格式

| 格式 | 含义 | 范例 |
|------|------|------|
| `[ip]` | 单 IP | `[192.168.1.100]` |
| `[ip/mask]` | CIDR | `[10.0.0.0/8]` |
| `[ipv6/mask]` | IPv6 CIDR | `[ff::01/64]` |
| `[ip]:port` | 单端口 | `[10.0.0.1]:443` |
| `[ip]:port,port` | 多端口 | `[10.0.0.1]:80,443` |
| `[ip/mask]:port` | CIDR + 端口 | `[10.0.0.0/8]:22` |
| `domain` | 域名 | `example.com` |
| `domain:port` | 域名 + 端口 | `api.example.com:443` |
| `*.domain` | 通配符域名 | `*.github.com` |
| `*.domain:port` | 通配符 + 端口 | `*.github.com:443` |

### 4.3 匹配优先级

1. **地址越长越精确，优先级越高**
2. **deny > allow**（冲突时）
3. **未在列表中的地址**：按 `default` 策略

### 4.4 配置示例

#### 仅允许 GitHub

```json
{
  "network": {
    "default": "deny",
    "allow": ["*.github.com:443"],
    "deny": []
  }
}
```

#### 禁止内网（CIDR 段）

```json
{
  "network": {
    "default": "allow",
    "allow": [],
    "deny": [
      "[10.0.0.0/8]",
      "[172.16.0.0/12]",
      "[192.168.0.0/16]"
    ]
  }
}
```

---

## 5. 默认文件访问策略

未在 sandbox.json 中配置的目录，应用以下默认策略：

| 权限 | 目录类型 | 目录列表 |
|------|---------|---------|
| **只读** | 项目目录中的受保护目录 | `.vscode` |
| **只读** | 根目录 | `/`（默认所有未声明可写目录为只读）|
| **读写** | 项目目录 | 除 `.trae` / `.vscode` / `.git` 之外的项目文件 |
| **读写** | 临时目录 | `~/AppData/Local/Temp`（Windows）/ `/tmp`（macOS/Linux）|
| **读写** | 缓存目录 | `~/.cache` |
| **读写** | 通用工具依赖目录 | `~/.local/lib` / `~/.local/bin`（pip/uv/uvx/npm/pnpm/cmake）|
| **读写** | 常用语言工具链 | Go/Java/Python/Node.js/Rust/C++ |

---

## 6. 命令运行策略

### 6.1 普通命令

| 白名单状态 | 行为 |
|----------|------|
| 在白名单 | 自动沙箱外运行 |
| 不在白名单 | 自动沙箱内运行；失败时询问沙箱外重试 |

### 6.2 高风险命令（如 rm -rf）

弹 3 选项卡：

1. **跳过**：不运行该命令
2. **添加到白名单**：将该命令前缀加入白名单
3. **运行**：本次在沙箱内运行

---

## 7. 与本项目 v5.2 沙箱白名单的关系

### 7.1 现状（v5.2）

项目已有：
- [delta-deployment-safety.md](../../../filework/.trae/rules/scenarios/2-deploy/delta-deployment-safety.md) —— 部署沙箱白名单
- service_manager.ps1 —— 服务管理脚本（管理沙箱白名单）

### 7.2 与 sandbox.json 的关系

| 维度 | 项目 service_manager | Trae sandbox.json |
|------|---------------------|-------------------|
| **粒度** | 服务级别（按服务配置）| 全局/项目级别 |
| **命令前缀** | 配置白名单 | 配置白名单 + 路径控制 |
| **网络控制** | 无 | 仅 Windows 支持 |
| **维护方** | 项目维护 | TRAE 维护 |

**结论**：两者互补：
- sandbox.json 用于**全局**沙箱策略
- service_manager.ps1 用于**项目**命令白名单

---

## 8. 推荐配置（excel-to-diagram 项目）

### 8.1 最小化 sandbox.json

```json
{
  "filesystem": {
    "readWrite": [
      "$WORKSPACE_FOLDER",
      "~/AppData/Local/Temp"
    ],
    "readOnly": []
  },
  "network": {
    "default": "allow",
    "allow": [
      "*.github.com:443",
      "localhost"
    ],
    "deny": [
      "[10.0.0.0/8]",
      "[172.16.0.0/12]",
      "[192.168.0.0/16]"
    ]
  }
}
```

### 8.2 命令白名单（设置 → 对话流 → 白名单）

```
# Staging 服务管理
bash tools/service_manager.sh

# DB 指纹
python tools/db_fingerprint.py

# 沙箱检查
bash tools/check_db_symlink.sh

# git 操作
git

# Python 测试
python tools/test.py
```

---

## 9. 参考

- [docs.trae.cn/ide/sandbox](https://docs.trae.cn/ide/sandbox)
- [docs.trae.cn/ide/auto-run-and-security](https://docs.trae.cn/ide/auto-run-and-security)
- [docs.trae.cn/ide_permission-and-approval](https://docs.trae.cn/ide_permission-and-approval)
- v5.4 深度研究：[2026-09-02-trae-ide-v5.4-deep-research.md](../../../excel-to-diagram/docs/governance/2026-09-02-trae-ide-v5.4-deep-research.md)