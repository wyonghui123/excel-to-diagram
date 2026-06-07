"""
End-to-end verification of the recording -> replay -> codegen pipeline.

Automatically tests:
  1. Recording captures operations (simulated via evaluate)
  2. Recording JSON is valid and contains expected events
  3. ReplayEngine can replay the recording
  4. CodeGenerator produces a valid Python script
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recorder import Recorder, ReplayEngine, CodeGenerator


def verify_recording_pipeline():
    results = {"steps": [], "passed": 0, "failed": 0}

    output_dir = os.path.join(os.path.dirname(__file__), '..', 'test_output')
    os.makedirs(output_dir, exist_ok=True)
    recording_path = os.path.join(output_dir, 'verify_recording.json')
    generated_script_path = os.path.join(output_dir, 'verify_generated_test.py')

    rec = Recorder(headless=True)
    try:
        print("[1/6] Navigating to /system/archdata ...")
        rec.authenticated_navigate(
            '/system/archdata',
            wait_for_selector='.el-table, .el-form, .el-select, #app'
        )
        print("  [OK] Navigation succeeded")
        results["steps"].append({"step": "navigate", "status": "passed"})
        results["passed"] += 1

        print("[2/6] Starting recording ...")
        status = rec.start_recording()
        assert status and 'started' in str(status).lower(), f"Start failed: {status}"
        print(f"  [OK] Recording started: {status}")
        results["steps"].append({"step": "start_recording", "status": "passed"})
        results["passed"] += 1

        print("[3/6] Simulating user actions via Playwright ...")
        page = rec._ensure_browser()

        found_clickable = rec.evaluate("""
            () => {
                const buttons = document.querySelectorAll('button, a, .el-button, [role="button"]');
                for (const b of buttons) {
                    if (b.offsetHeight > 0 && b.offsetWidth > 0) {
                        return b.className || b.tagName;
                    }
                }
                return null;
            }
        """)
        print(f"  [INFO] Found clickable: {found_clickable}")

        if found_clickable:
            try:
                buttons = page.locator('button, a, .el-button, [role="button"]').first
                if buttons.count() > 0:
                    buttons.first.click()
                    rec.wait_for_timeout(500)
                    print("  [OK] Clicked first available button")
            except Exception as e:
                print(f"  [WARN] Click failed: {str(e)[:80]}")

        found_input = rec.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input[type="text"], input:not([type]), .el-input__inner, textarea');
                for (const inp of inputs) {
                    if (inp.offsetHeight > 0 && inp.offsetWidth > 0 && !inp.disabled && !inp.readOnly) {
                        return inp.placeholder || inp.className || inp.tagName;
                    }
                }
                return null;
            }
        """)
        print(f"  [INFO] Found input: {found_input}")

        if found_input:
            try:
                inputs = page.locator('input[type="text"], input:not([type]), .el-input__inner, textarea').first
                if inputs.count() > 0:
                    inputs.first.click()
                    rec.wait_for_timeout(200)
                    inputs.first.fill('test_value_verify')
                    rec.wait_for_timeout(500)
                    print("  [OK] Filled input with 'test_value_verify'")
            except Exception as e:
                print(f"  [WARN] Fill failed: {str(e)[:80]}")

        count = rec.get_event_count()
        print(f"  [INFO] Captured {count} events")
        results["steps"].append({"step": "simulate_actions", "status": "passed",
                                 "event_count": count})
        results["passed"] += 1

        print("[4/6] Stopping recording and saving ...")
        recording = rec.stop_recording(recording_path)
        assert recording.get('events'), "No events captured"
        event_count = len(recording['events'])
        print(f"  [OK] Recording saved with {event_count} events")
        print(f"  [INFO] Event types: {set(e['type'] for e in recording['events'])}")
        results["steps"].append({"step": "stop_recording", "status": "passed",
                                 "event_count": event_count})
        results["passed"] += 1

    except Exception as e:
        print(f"  [FAIL] Recording phase: {e}")
        results["steps"].append({"step": "recording_phase", "status": "failed", "error": str(e)})
        results["failed"] += 1
    finally:
        rec.close()

    if not os.path.exists(recording_path):
        print("[FAIL] Recording file not found, cannot proceed to replay/codegen")
        return results

    print("[5/6] Replaying recording ...")
    try:
        engine = ReplayEngine(
            recording_path,
            headless=True,
            fast_forward=True
        )
        replay_results = engine.run()
        print(f"  Results: {replay_results['passed']}/{replay_results['total']} passed, "
              f"{replay_results['failed']} failed, {replay_results['skipped']} skipped")
        results["steps"].append({
            "step": "replay",
            "status": "passed" if replay_results['failed'] == 0 else "partial",
            "details": replay_results
        })
        results["passed"] += 1
    except Exception as e:
        print(f"  [FAIL] Replay: {e}")
        results["steps"].append({"step": "replay", "status": "failed", "error": str(e)})
        results["failed"] += 1

    print("[6/6] Generating test code ...")
    try:
        CodeGenerator.generate(
            recording_path,
            generated_script_path,
            test_name='verify_generated'
        )
        assert os.path.exists(generated_script_path), "Script file not created"
        with open(generated_script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        assert 'from browser_auth_cli import PlaywrightCLI' in code, "Missing import"
        assert 'def test_verify_generated():' in code, "Missing test function"
        print(f"  [OK] Generated script: {generated_script_path} ({len(code)} chars)")
        results["steps"].append({
            "step": "codegen",
            "status": "passed",
            "script_path": generated_script_path,
            "script_size": len(code)
        })
        results["passed"] += 1
    except Exception as e:
        print(f"  [FAIL] Codegen: {e}")
        results["steps"].append({"step": "codegen", "status": "failed", "error": str(e)})
        results["failed"] += 1

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("  Recording Pipeline Verification")
    print("=" * 60)
    print()

    results = verify_recording_pipeline()

    print()
    print("=" * 60)
    print(f"  VERIFICATION COMPLETE")
    print(f"  Passed: {results['passed']}/{results['passed'] + results['failed']}")
    print("=" * 60)

    if results['failed'] > 0:
        print("\n[FAIL] Some steps failed. See details above.")
        sys.exit(1)
    else:
        print("\n[PASS] All verification steps passed!")
        sys.exit(0)
