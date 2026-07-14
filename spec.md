# SPEC: L17 智能 Delta 部署实现

## 任务概述
实现 content-addressed delta 部署: rebuild_zip.py --delta 只打包 changed files,
deploy.sh PHASE 0.5 智能提取, 部署包从 ~80MB 降至 ~1-5MB.

## 涉及文件（白名单）
- tools/manifest_utils.py
- tools/rebuild_zip.py
- tools/tests/conftest.py
- tools/tests/test_delta_manifest.py
- deploy_bundle/lib/smart_extract.sh
- deploy_bundle/lib/sha256_compare.sh
- deploy_bundle/tools/post_deploy_check.py
- docs/superpowers/plans/2026-07-14-smart-delta-deploy.md
- docs/superpowers/specs/2026-07-14-smart-delta-deploy-design.md

## 涉及文件（黑名单，绝对禁止修改）
- d:\filework\excel-to-diagram\**    (主工作树)
- d:\filework\.git\**                  (git metadata)
- meta/server.py (后端服务不改动)
- src/ (前端不改动)

## 完成标准
- [ ] manifest_utils.py: FileEntry/Manifest/parse/generate/compute_delta/build_delta_zip
- [ ] rebuild_zip.py --delta 集成, is_delta guards 跳过全量检查
- [ ] test_delta_manifest.py 4/4 PASS
- [ ] Delta zip 比 full zip 小 90%+
