# Excel to Diagram - 快速部署指南

## 📦 首次部署（已上传文件到 /opt/app/dist/）

```bash
cd /opt/app
chmod +x deploy.sh
./deploy.sh v20250416_001
```

## 🔄 后续更新流程

### 1. 本地构建并打包
```bash
# 进入项目目录
cd excel-to-diagram

# 构建前端
npm run build

# 打包（在dist目录内）
cd dist
zip -r ../excel-to-diagram-v20250416_002.zip .
```

### 2. 上传到服务器
通过堡垒机上传 `excel-to-diagram-v20250416_002.zip` 到 `/opt/app/`

### 3. 服务器上执行部署
```bash
cd /opt/app

# 解压到新目录
unzip -q excel-to-diagram-v20250416_002.zip -d dist-v20250416_002

# 执行部署
./deploy.sh v20250416_002
```

## ⚡ 常用命令

| 命令 | 说明 |
|------|------|
| `./deploy.sh v20250416_003` | 部署新版本 |
| `./rollback.sh` | 回滚到上一版本 |
| `./rollback.sh v20250415_001` | 回滚到指定版本 |
| `./stop.sh` | 停止服务 |
| `./start.sh` | 启动服务 |
| `tail -f server.log` | 查看日志 |

## 📁 目录结构

```
/opt/app/
├── current -> releases/v20250416_002/    # 当前运行版本
├── releases/                              # 所有版本
│   ├── v20250416_001/
│   ├── v20250416_002/
│   └── v20250416_003/
├── backup/                               # 备份
├── logs/                                 # 日志
├── deploy.sh                             # 部署脚本
├── rollback.sh                           # 回滚脚本
└── server.py                             # Python服务器
```

## ✅ 部署检查清单

更新前：
- [ ] 代码已提交并构建成功
- [ ] 版本号格式正确 (vYYYYMMDD_NNN)
- [ ] 已通知相关人员

更新后：
- [ ] 部署脚本显示成功
- [ ] `curl http://localhost` 返回200
- [ ] 页面内容正确
- [ ] 关键功能正常

## 🆘 常见问题

**Q: 部署失败怎么办？**  
A: 查看日志 `tail -f logs/deploy_20250416.log`，然后执行 `./rollback.sh` 回滚

**Q: 如何查看当前版本？**  
A: `ls -la /opt/app/current`

**Q: 磁盘空间不足？**  
A: 清理旧版本 `rm -rf /opt/app/releases/v20250415_*`

**Q: 端口被占用？**  
A: `lsof -i:80` 查看占用进程，然后 `kill -9 <PID>`
