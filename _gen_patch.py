"""
生成 worktree 的 patch: 把主工作树当前未提交改动保存为 patch
"""
import subprocess, os
os.chdir(r'd:\filework\excel-to-diagram')

# 生成 patch (UTF-8 binary mode, 避免 CRLF/LF 问题)
result = subprocess.run(
    ['git', 'diff', '--', 'meta/', 'src/'],
    capture_output=True, check=True
)
patch_bytes = result.stdout

# 写文件
patch_path = r'd:\filework\excel-to-diagram\_import_dialog_fixes_v2.patch'
with open(patch_path, 'wb') as f:
    f.write(patch_bytes)

print(f"Patch size: {len(patch_bytes)} bytes")
print(f"First 100 bytes: {patch_bytes[:100]!r}")
