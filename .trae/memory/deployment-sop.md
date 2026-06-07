# Excel to Diagram 部署SOP - AI记忆文档

> **重要**: 此文档用于确保AI助手在换会话或重启后能记住完整的部署流程

---

## 📋 项目信息

- **项目名称**: excel-to-diagram
- **部署目标**: http://172.20.59.7:80
- **技术栈**: Vue.js + Python 2.5 SimpleHTTPServer
- **部署方式**: 手动上传zip + 脚本部署

---

## 🎯 核心SOP（3步骤）

### 步骤1: 本地打包
```bash
# 在项目根目录执行
./build-and-notify.sh
# 输出: deploy-vYYYYMMDD_NNN.zip
```

### 步骤2: 上传到服务器
- 通过堡垒机上传zip到 `/opt/app/`

### 步骤3: 执行部署
```bash
# 使用健壮部署脚本
cd /opt/app && ./deploy-robust.sh deploy-vYYYYMMDD_NNN.zip
```

---

## 🔧 关键文件位置

| 文件 | 路径 | 作用 |
|------|------|------|
| 健壮部署脚本 | `/opt/app/deploy-robust.sh` | 主部署脚本（7阶段） |
| 回滚脚本 | `/opt/app/rollback.sh` | 一键回滚 |
| 服务器脚本 | `/opt/app/server.py` | Python HTTP服务器 |
| 当前版本 | `/opt/app/current/` | 软链接指向当前版本 |
| 版本目录 | `/opt/app/releases/` | 所有历史版本 |
| 备份目录 | `/opt/app/backup/` | 备份版本 |

---

## 🚨 常见问题及解决

### 问题1: Permission denied
**解决**: 脚本已内置权限修复，或手动执行
```bash
chmod +x /opt/app/deploy-robust.sh
```

### 问题2: "No such file or directory: '/opt/app/dist'"
**原因**: server.py使用了错误的SCRIPT_DIR
**解决**: server.py已修复，使用固定路径 `/opt/app/current`

### 问题3: 新功能不生效
**原因**: 
1. 代码未commit就打包
2. 浏览器缓存
**解决**:
```bash
# 1. 确保git commit后再打包
git add . && git commit -m "xxx"
npm run build

# 2. 强制刷新浏览器 Ctrl+F5
```

### 问题4: HTTP 404
**原因**: current软链接指向错误
**解决**:
```bash
rm -f /opt/app/current
ln -s /opt/app/releases/vYYYYMMDD_NNN /opt/app/current
```

---

## 📁 目录结构标准

```
/opt/app/
├── current -> releases/v20260416_003/    # 软链接
├── server.py                              # HTTP服务器
├── deploy-robust.sh                       # 部署脚本
├── rollback.sh                            # 回滚脚本
├── server.log                             # 运行日志
├── server.pid                             # 进程ID
├── releases/                              # 版本目录
│   ├── v20260416_001/
│   ├── v20260416_002/
│   └── v20260416_003/
│       ├── index.html
│       └── assets/
└── backup/                                # 备份目录
```

---

## 🔄 回滚流程

```bash
# 方式1: 使用回滚脚本
/opt/app/rollback.sh

# 方式2: 手动回滚
pkill -f python
rm -f /opt/app/current
ln -s /opt/app/releases/v20260416_002 /opt/app/current
cd /opt/app/current && nohup python /opt/app/server.py > /opt/app/server.log 2>&1 &
```

---

## 📝 版本命名规范

- 格式: `vYYYYMMDD_NNN`
- 示例: `v20260416_003`
- 生成脚本: `build-and-notify.sh` 自动生成

---

## ✅ 部署验证清单

- [ ] zip文件上传到 `/opt/app/`
- [ ] 执行 `./deploy-robust.sh deploy-vXXX.zip`
- [ ] 看到 "HTTP 200 OK"
- [ ] 浏览器访问 http://172.20.59.7:80 正常
- [ ] 看到 "下载彩色HTML" 按钮
- [ ] 看到 "复制代码" 按钮

---

## 🆘 紧急联系

如果部署完全失败：
1. 停止服务: `pkill -f python`
2. 检查日志: `cat /opt/app/server.log`
3. 检查目录: `ls -la /opt/app/current/`
4. 手动启动测试: `cd /opt/app/current && python -m SimpleHTTPServer 8080`

---

## 💡 关键代码片段

### server.py（已修复版）
```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
import SimpleHTTPServer
import SocketServer
import os
import sys

PORT = 80
# 使用绝对路径，不依赖工作目录
os.chdir('/opt/app/current')

class Handler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

try:
    httpd = SocketServer.TCPServer(("", PORT), Handler)
    print "Server started on port %d" % PORT
    httpd.serve_forever()
except Exception, e:
    print "Error: %s" % str(e)
    sys.exit(1)
```

### 健壮部署脚本核心逻辑
```bash
# 7阶段部署
1. preflight_check      # 前置检查
2. pre_deploy_verify    # 预部署验证（临时目录解压）
3. backup_current       # 备份当前版本
4. atomic_deploy        # 原子切换
5. start_service        # 启动服务
6. health_check         # 健康检查（HTTP+功能）
7. post_deploy_cleanup  # 清理旧版本
```

---

## 📌 记忆锚点

**当用户说以下关键词时，立即查阅此文档：**
- "部署"
- "更新"
- "打包"
- "上传"
- "服务器"
- "新版本"
- "回滚"
- "404"
- "权限"
- "失败"

---

**最后更新**: 2026-04-16
**版本**: v1.0
