# deploy_bundle/

One-click deploy bundle. SFTP to /tmp/ on remote.

## 瀹屾暣鏂囨。 (AI Agent 蹇呰)
D:\filework\release-prep-worktree\DEPLOY_INFRASTRUCTURE.md

## 涓婁紶
MobaXterm SFTP: drag deploy_bundle/ to /tmp/

## 閮ㄧ讲
bash /tmp/deploy_bundle/deploy.sh --version v20260703_002 --port 5001

## 鍥炴粴
bash /tmp/deploy_bundle/rollback.sh --to <v> --port <p>

## 鐘舵€?/ 閲嶅惎
bash /tmp/deploy_bundle/status.sh
bash /tmp/deploy_bundle/restart.sh

## 鐩戞帶
bash /tmp/deploy_bundle/watch.sh --loop 30
bash /tmp/deploy_bundle/watch.sh --auto-recover
bash /tmp/deploy_bundle/watch.sh --rollback-on-fail

## 鍘嗗彶
bash /tmp/deploy_bundle/deploy_history.sh
bash /tmp/deploy_bundle/deploy_history.sh --info v20260703_002
bash /tmp/deploy_bundle/deploy_history.sh --switch v20260630_003 --port 5000

## 娴嬭瘯 (杩滅)
/opt/miniconda3-py39/bin/python /tmp/deploy_bundle/tests/test_rollback_parallel.py
/opt/miniconda3-py39/bin/python /tmp/deploy_bundle/tests/test_frontend_dir.py
