# AI Memory: Excel to Diagram 部署流程

## 快速响应模板

当用户说以下关键词时：
- "打包新版本"
- "按SOP部署"
- "部署"
- "发布"

### 立即执行：

1. **构建打包**
   ```bash
   npm run build
   ```

2. **生成部署包**
   - 版本号格式：`vYYYYMMDD_NNN`
   - 文件名：`deploy-vYYYYMMDD_NNN.zip`
   - 包含：dist/ + deploy-auto.sh + rollback.sh

3. **回复用户**
   ```
   ✅ 打包完成！

   📦 文件名：deploy-vYYYYMMDD_NNN.zip
   📊 文件大小：X.XX MB
   🔢 版本号：vYYYYMMDD_NNN

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   第3步执行命令（复制以下全部内容）：
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   cd /opt/app && ./deploy-auto.sh deploy-vYYYYMMDD_NNN.zip

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

## 关键信息

- **服务器：** 172.20.59.7 (CentOS 7, Python 2.5)
- **部署路径：** /opt/app/
- **端口：** 80
- **上传方式：** 堡垒机
- **当前状态：** 已初始化，脚本已授权

## 注意事项

1. deploy-auto.sh 已包含权限修复逻辑，无需手动 chmod
2. Windows 打包的 zip 会有路径分隔符警告，不影响部署
3. 部署失败会自动回滚
4. 保留最近3个版本

## 参考文档

- 详细SOP：DEPLOY_SOP_FINAL.md
- 部署脚本：deploy-auto.sh
- 回滚脚本：rollback.sh
