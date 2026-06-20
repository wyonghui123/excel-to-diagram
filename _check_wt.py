"""Check git worktree list."""
import subprocess
import os

os.chdir(r'D:\filework\excel-to-diagram')
result = subprocess.run(['git', 'worktree', 'list'], capture_output=True, text=True, shell=True)
with open(r'D:\filework\excel-to-diagram\_wt_status.log', 'w') as f:
    f.write("RC: " + str(result.returncode) + "\n")
    f.write("STDOUT:\n" + result.stdout + "\n")
    f.write("STDERR:\n" + result.stderr + "\n")
print(result.stdout)
print("STDERR:", result.stderr)
print("RC:", result.returncode)