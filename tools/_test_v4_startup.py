"""test v4 startup time"""
import subprocess, time, sys, os
from pathlib import Path
import tempfile, shutil

root = Path(tempfile.mkdtemp(prefix="v4_test_"))
v4 = root / "meta"
shutil.copytree(Path("D:/filework/worktrees/release-prep/build/verify/meta"), v4)
env = os.environ.copy()
env["PORT"] = "5001"
env["JWT_SECRET_KEY"] = "test"
proc = subprocess.Popen(
    [sys.executable, "server.py"],
    cwd=str(v4),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
for i in range(20):
    time.sleep(1)
    if proc.poll() is not None:
        print(f"EXITED at {i+1}s, code={proc.returncode}")
        out = proc.stdout.read().decode("utf-8", errors="replace")[-3000:]
        print(out)
        break
    print(f"  {i+1}s alive")
else:
    print("Still alive after 20s")
    proc.terminate()
    out = proc.stdout.read().decode("utf-8", errors="replace")[-3000:]
    print(out)
shutil.rmtree(root, ignore_errors=True)
