"""Run all audit fix scripts and capture output."""
import subprocess
import sys

LOG = r"d:\filework\excel-to-diagram\_audit_fix_run.log"


def run(cmd, cwd=None):
    print(f"\n>>> {cmd}")
    result = subprocess.run(
        cmd,
        cwd=cwd or r"d:\filework\excel-to-diagram",
        capture_output=True,
        text=True,
        shell=True,
    )
    print(f"RC: {result.returncode}")
    if result.stdout:
        print("STDOUT:")
        print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    return result


def main():
    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    log("=" * 60)
    log("[RUN 1] fix_audit_admin_parentheses.py --dry-run")
    log("=" * 60)
    r = run([sys.executable, "scripts/fix_audit_admin_parentheses.py", "--dry-run"])
    log(r.stdout or "")
    log(r.stderr or "")

    log("\n" + "=" * 60)
    log("[RUN 2] backfill_audit_transaction_id.py --dry-run")
    log("=" * 60)
    r = run([sys.executable, "scripts/backfill_audit_transaction_id.py", "--dry-run"])
    log(r.stdout or "")
    log(r.stderr or "")

    log("\n" + "=" * 60)
    log("[RUN 3] verify_audit_fix.py (baseline)")
    log("=" * 60)
    r = run([sys.executable, "scripts/verify_audit_fix.py"])
    log(r.stdout or "")
    log(r.stderr or "")

    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    print(f"\n[LOG SAVED] {LOG}")


if __name__ == "__main__":
    main()