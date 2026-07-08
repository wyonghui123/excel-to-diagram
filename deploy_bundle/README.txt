# _deploy_bundle/

一键部署包 (MobaXterm SFTP 拖到 /tmp/)

## 上传
MobaXterm SFTP: 拖 _deploy_bundle/ → 远端 /tmp/

## 部署
bash /tmp/_deploy_bundle/deploy.sh --version v20260707_002 --port 5001

## 回滚
bash /tmp/_deploy_bundle/rollback.sh --to <v> --port <p>

## 文件清单
- deploy.sh            部署入口 (含 precheck + smoke)
- precheck.sh          部署前 7 项检查
- smoke_test.sh        部署后 5 项真实功能测试
- rollback.sh          通用回滚
- unified_server.py    静态文件 + API 代理
- lib/common.sh        共享库
- deploy-v20260707_002.zip  代码包
- README.txt           本文件

生成时间: 2026-07-07 19:18:32
