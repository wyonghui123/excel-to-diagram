# Excel to Diagram 部署 - 快速参考卡

## 🚀 一键部署
```bash
cd /opt/app && ./deploy-robust.sh deploy-v20260416_004.zip
```

## 📂 关键路径
- 应用目录: `/opt/app/`
- 当前版本: `/opt/app/current/`
- 版本目录: `/opt/app/releases/`
- 服务器日志: `/opt/app/server.log`

## 🔧 常用命令
```bash
# 查看状态
curl -I http://localhost
ls -la /opt/app/current/

# 重启服务
pkill -f python
cd /opt/app/current && nohup python /opt/app/server.py > /opt/app/server.log 2>&1 &

# 回滚
/opt/app/rollback.sh

# 查看日志
tail -f /opt/app/server.log
```

## ⚠️ 常见错误
| 错误 | 解决 |
|------|------|
| Permission denied | `chmod +x deploy-robust.sh` |
| No such file dist | server.py已修复，使用current目录 |
| HTTP 404 | 检查current软链接指向 |
| 新功能不显示 | 强制刷新浏览器 Ctrl+F5 |

## 📝 版本命名
`vYYYYMMDD_NNN` 例如: `v20260416_003`

## ✅ 验证部署成功
- HTTP 200 OK
- 页面显示 "AA Diagram"
- 有"下载彩色HTML"按钮
- 有"复制代码"按钮
