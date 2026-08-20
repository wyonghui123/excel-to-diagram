"""Run all e2e_spec_08 tests sequentially and report results."""
import subprocess
import sys
import os

# Test files in order (modified ones first to verify fixes)
TEST_FILES = [
    'meta/tests/e2e_spec_08_stale_rederive.py',
    'meta/tests/e2e_spec_08_multi_role_exclude.py',
    'meta/tests/e2e_spec_08_cartesian_product.py',
    'meta/tests/e2e_spec_08_wildcard_exclude.py',
    'meta/tests/e2e_spec_08_manual_intent_priority.py',
    'meta/tests/e2e_spec_08_value_help_regression.py',
    'meta/tests/e2e_spec_08_read_write_regression.py',
    'meta/tests/e2e_spec_08_permission_regression.py',
    'meta/tests/e2e_spec_08_parent_children_derivation.py',
]


def extract_summary(output):
    """Extract '总计: X/Y 通过' line and PASS/FAIL counts from output."""
    lines = output.splitlines()
    summary = ''
    pass_count = 0
    fail_count = 0
    for line in lines:
        if '总计:' in line and '通过' in line:
            summary = line.strip()
        elif '[PASS]' in line:
            pass_count += 1
        elif '[FAIL]' in line:
            fail_count += 1
    return summary, pass_count, fail_count


def main():
    print("=" * 80)
    print(f"Running {len(TEST_FILES)} e2e_spec_08 tests")
    print("=" * 80)

    all_results = []
    for i, tf in enumerate(TEST_FILES, 1):
        print(f"\n[{i}/{len(TEST_FILES)}] Running {tf}...")
        print("-" * 80)
        try:
            result = subprocess.run(
                [sys.executable, tf],
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, 'BASE_URL': 'http://localhost:3011'},
            )
            output = result.stdout + result.stderr
            # Print last 30 lines
            lines = output.splitlines()
            for line in lines[-30:]:
                print(line)
            summary, p, f = extract_summary(output)
            all_results.append((tf, summary, p, f, result.returncode))
            print(f"\n  >> Summary: {summary}")
            print(f"  >> PASS={p}, FAIL={f}, exit={result.returncode}")
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {tf} exceeded 300s")
            all_results.append((tf, 'TIMEOUT', 0, 0, -1))
        except Exception as e:
            print(f"  [ERROR] {tf}: {e}")
            all_results.append((tf, f'ERROR: {e}', 0, 0, -1))

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    total_pass = 0
    total_fail = 0
    for tf, summary, p, f, rc in all_results:
        total_pass += p
        total_fail += f
        status_emoji = 'OK' if f == 0 and rc == 0 else 'FAIL'
        print(f"  [{status_emoji}] {os.path.basename(tf)}: {summary} (exit={rc})")
    print(f"\nTotal: PASS={total_pass}, FAIL={total_fail}")
    print(f"Overall: {'ALL PASS' if total_fail == 0 else 'HAS FAILURES'}")


if __name__ == '__main__':
    main()
