部署包 (BUNDLE) - v20260630_001
============================

您需要的 8 个文件都在这个文件夹。
打开此文件夹后,全选,然后 **一起拖** 到 MobaXterm 的 SFTP 浏览器的 /tmp/ 目录。


文件清单 (8 个)
--------------------
1. deploy-v20260630_001.zip          (15 MB) <-- 核心部署包,含 17 个 Python 轮子
2. deploy-full-v20260630_001.sh      (15 KB) <-- 主部署脚本,一键跑 B.1-B.9 + C.1 验证
3. deploy-rollback-v20260630_001.sh  (6 KB)  <-- 回滚脚本(出问题用)
4. HEALTH-CHECK-20260630_001.sh      (6 KB)  <-- 独立健康检查(不依赖部署链)
5. DEPLOY-CHEATSHEET-20260630_001.txt (8 KB) <-- 一页纸速查表(打印一份)
6. DEPLOY-MANUAL-20260630_001.md     (11 KB) <-- 完整操作手册(11 步骤 + 5 常见问题)
7. UPLOAD-GUIDE-20260630_001.md      (8 KB)  <-- 上传指引(MobaXterm/FinalShell)
8. MD5SUMS-20260630_001.txt          (0.7 KB) <-- 8 个文件的 MD5 校验,上传后用


操作顺序
--------------------
A. 上传 (10 分钟)
   1. 把这 8 个文件 **一起拖** 到 MobaXterm 左侧的 /tmp/ 目录
   2. 等 zip 上传完成 (看进度条)
   3. 上传完后,在 Web SSH 终端运行:
      sed -i 's/\r$//' /tmp/MD5SUMS-20260630_001.txt
      md5sum -c /tmp/MD5SUMS-20260630_001.txt
   4. 应该看到 8 行 "OK" (有 1 行 "improperly formatted" 是注释,可忽略)

B. 部署 (5-8 分钟)
   5. 在 Web SSH 终端运行:
      chmod +x /tmp/deploy-full-v20260630_001.sh
      bash /tmp/deploy-full-v20260630_001.sh
   6. 看到 "DEPLOY COMPLETE" + "VERIFICATION RESULT: 10 / 10" 就是成功

C. 验证
   7. 在浏览器打开: http://172.20.59.7:8081/
   8. 登录: admin / Admin@2026!Init (登录后立即改密码)


卡住时
--------------------
在 Web SSH 终端运行:
   bash /tmp/HEALTH-CHECK-20260630_001.sh
把输出贴给我,我帮你看。

或看完整部署日志:
   tail -100 /opt/app/shared/logs/deploy-run.log


注意事项
--------------------
- 服务器没有外网访问,所有 Python 依赖都已打包在 zip 里 (backend/wheels/)
- 如果 B.3 步骤 (pip install) 失败,检查 wheels/ 目录是否解压成功
  ls /opt/app/deployments/v20260630_001/backend/wheels/   (应该看到 17 个 .whl 文件)
- 任何脚本出错会立即停止 (set -e),绝对不会"假成功"


版本: v20260630_001
日期: 2026-06-30
SHA: 25ada5f (git commit)
部署包 MD5: 737464cbd15b908ab1a861afd33c621c
