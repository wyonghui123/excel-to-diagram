"""
Recording layer for E2E test automation.

Three components in one module:
  - Recorder: captures user actions during manual E2E testing
  - ReplayEngine: replays recorded actions via PlaywrightCLI
  - CodeGenerator: converts recording JSON to Python PlaywrightCLI test script

Workflow:
  1. Recorder captures manual operations -> recording.json
  2. ReplayEngine replays recording.json for verification
  3. CodeGenerator converts recording.json -> test_script.py (reusable automated test)

Usage example:
  from test_helpers.recorder import Recorder, ReplayEngine, CodeGenerator

  # Step 1: Record
  rec = Recorder(headless=False)
  rec.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
  rec.start_recording()
  input('[INFO] Manual test. Press Enter when done...')
  rec.stop_recording('test_output/my_test.json')
  rec.close()

  # Step 2: Replay (verify)
  replay = ReplayEngine('test_output/my_test.json')
  results = replay.run()
  print(results)

  # Step 3: Generate code
  CodeGenerator.generate('test_output/my_test.json', 'test_output/test_archdata.py')
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI


class Recorder(PlaywrightCLI):
    """
    Extends PlaywrightCLI with user action recording capability.

    Injects record_helpers.js to capture clicks, inputs, navigation
    during manual browser testing in non-headless mode.

    Usage:
        rec = Recorder(headless=False)
        rec.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
        rec.start_recording()
        input('[INFO] Perform manual test steps, then press Enter...')
        rec.stop_recording('test_output/recording.json')
        rec.close()
    """

    def __init__(self, headless: bool = False, **kwargs):
        super().__init__(headless=headless, **kwargs)
        self._recording = False
        self._recording_start_time = None
        self._initial_url = None
        self._recording_seq = 0

    def _inject_recorder(self):
        """Inject record_helpers.js into the page."""
        if getattr(self, '_recorder_injected', False):
            return
        helpers_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'record_helpers.js'
        )
        with open(helpers_path, 'r', encoding='utf-8') as f:
            js_content = f.read()
        idx = js_content.find('window.__recorder__ =')
        if idx == -1:
            raise RuntimeError("record_helpers.js format error: window.__recorder__ = not found")
        script = js_content[idx:]
        page = self._ensure_browser()
        page.evaluate(script)
        self._recorder_injected = True

    def start_recording(self) -> str:
        """
        Start capturing user actions in the browser.

        Must be called after authenticated_navigate().

        Returns:
            Status message string.
        """
        page = self._ensure_browser()
        self._inject_recorder()
        self._initial_url = self.evaluate("() => window.location.href")
        result = self.evaluate("window.__recorder__.start()")
        self._recording = True
        self._recording_start_time = time.time()
        self._recording_seq = 0
        return result

    def stop_recording(self, output_path: str = None) -> Dict:
        """
        Stop recording and retrieve captured events.

        Args:
            output_path: If provided, save recording JSON to this path.

        Returns:
            Recording dict with metadata and events.
        """
        if not self._recording:
            return {"error": "not recording"}
        events = self.evaluate("window.__recorder__.stop()")
        self._recording = False
        duration_ms = (time.time() - self._recording_start_time) * 1000

        recording = {
            "version": "1.0",
            "metadata": {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "base_url": self._initial_url or "",
                "event_count": len(events),
                "duration_ms": round(duration_ms, 0)
            },
            "events": events
        }

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(recording, f, ensure_ascii=False, indent=2)
            print(f"[RECORDER] Recording saved: {output_path} "
                  f"({len(events)} events, {duration_ms:.0f}ms)")

        return recording

    def get_events(self) -> List[Dict]:
        """
        Get events captured so far without stopping recording.

        Returns:
            List of event dicts.
        """
        if not self._recording:
            return []
        return self.evaluate("window.__recorder__.getEvents()")

    def get_event_count(self) -> int:
        """Get count of events captured so far."""
        if not self._recording:
            return 0
        return self.evaluate("window.__recorder__.getEventCount()")

    def is_recording(self) -> bool:
        return self._recording


class ReplayEngine:
    """
    Replays a recorded session via PlaywrightCLI.

    Usage:
        engine = ReplayEngine('test_output/recording.json')
        results = engine.run()
        print(f"Passed: {results['passed']}/{results['total']}")
    """

    def __init__(
        self,
        recording_path: str,
        headless: bool = True,
        fast_forward: bool = True,
        base_url: str = "http://localhost:3004"
    ):
        """
        Args:
            recording_path: Path to recording JSON file.
            headless: Run in headless mode (True) or visible (False).
            fast_forward: If True, execute as fast as possible.
                          If False, respect original timing.
            base_url: Base URL for navigation.
        """
        self.recording_path = recording_path
        self.headless = headless
        self.fast_forward = fast_forward
        self.base_url = base_url
        self._cli = None
        self._recording = None
        self._results = []

    def load(self) -> Dict:
        """Load recording JSON from path."""
        with open(self.recording_path, 'r', encoding='utf-8') as f:
            self._recording = json.load(f)
        return self._recording

    def run(self) -> Dict:
        """
        Execute all recorded events.

        Returns:
            {
                total: int,
                passed: int,
                failed: int,
                skipped: int,
                results: [{seq, type, status, selector, error}]
            }
        """
        if self._recording is None:
            self.load()

        events = self._recording.get('events', [])
        if not events:
            return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "results": []}

        self._cli = PlaywrightCLI(headless=self.headless)
        self._results = []

        try:
            nav_event = events[0]
            if nav_event.get('type') == 'navigate':
                target_path = nav_event.get('value', '/')
                if target_path and target_path != '/':
                    self._cli.authenticated_navigate(
                        target_path,
                        base_url=self.base_url,
                        wait_for_selector='.el-table, .el-form, .el-select, #app'
                    )
                else:
                    self._cli.authenticated_navigate(
                        '/',
                        base_url=self.base_url,
                        wait_for_selector='#app'
                    )
                self._results.append({
                    "seq": 0, "type": "navigate",
                    "status": "passed", "target": target_path
                })

            prev_timestamp = events[0].get('timestamp', 0)
            action_events = [e for e in events if e.get('type') != 'navigate']

            for event in action_events:
                result = self._replay_event(event, prev_timestamp)
                self._results.append(result)
                if not self.fast_forward:
                    prev_timestamp = event.get('timestamp', prev_timestamp)

            for nav_event in [e for e in events if e.get('type') == 'navigate' and e.get('seq', 0) > 0]:
                target_path = nav_event.get('value', '/')
                self._cli.authenticated_navigate(
                    target_path,
                    base_url=self.base_url,
                    wait_for_selector='.el-table, .el-form, #app'
                )
                self._results.append({
                    "seq": nav_event.get('seq'),
                    "type": "navigate",
                    "status": "passed",
                    "target": target_path
                })

        except Exception as e:
            self._results.append({
                "seq": -1, "type": "fatal",
                "status": "failed", "error": str(e)[:200]
            })
        finally:
            if self._cli:
                self._cli.close()

        passed = sum(1 for r in self._results if r.get('status') == 'passed')
        failed = sum(1 for r in self._results if r.get('status') == 'failed')
        skipped = sum(1 for r in self._results if r.get('status') == 'skipped')

        return {
            "total": len(action_events) + 1,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "results": self._results
        }

    def _replay_event(self, event: Dict, prev_timestamp: float) -> Dict:
        """Execute a single recorded event."""
        event_type = event.get('type')
        seq = event.get('seq', 0)
        target = event.get('target', {})
        selector = target.get('selector', '')
        fallbacks = target.get('fallback_selectors', [])
        value = event.get('value')
        text = target.get('text', '')
        tag = target.get('tag', '')

        selectors_to_try = [s for s in [selector] + fallbacks if s]

        base_result = {"seq": seq, "type": event_type, "selector": selector}

        if not self.fast_forward:
            delay_s = (event.get('timestamp', prev_timestamp) - prev_timestamp) / 1000.0
            if delay_s > 0.01 and delay_s < 60:
                time.sleep(min(delay_s, 5.0))
        else:
            self._cli.wait_for_timeout(200)

        try:
            if event_type == 'click':
                return self._try_click(selectors_to_try, text, base_result)

            elif event_type == 'dblclick':
                result = self._try_click(selectors_to_try, text, base_result)
                if result['status'] == 'passed':
                    try:
                        page = self._cli._ensure_browser()
                        page.dblclick(result.get('used_selector', selector))
                        self._cli.wait_for_timeout(500)
                    except Exception:
                        pass
                return result

            elif event_type == 'input':
                return self._try_fill(selectors_to_try, value, base_result)

            elif event_type == 'select':
                return self._try_select(selectors_to_try, value, base_result)

            elif event_type == 'check':
                return self._try_click(selectors_to_try, text, base_result)

            elif event_type == 'toggle':
                return self._try_click(selectors_to_try, text, base_result)

            elif event_type == 'keydown':
                if value == 'Enter':
                    try:
                        page = self._cli._ensure_browser()
                        page.keyboard.press('Enter')
                        self._cli.wait_for_timeout(300)
                        base_result['status'] = 'passed'
                    except Exception as e:
                        base_result['status'] = 'failed'
                        base_result['error'] = str(e)[:150]
                elif value == 'Escape':
                    try:
                        page = self._cli._ensure_browser()
                        page.keyboard.press('Escape')
                        self._cli.wait_for_timeout(200)
                        base_result['status'] = 'passed'
                    except Exception as e:
                        base_result['status'] = 'failed'
                        base_result['error'] = str(e)[:150]
                else:
                    base_result['status'] = 'skipped'
                    base_result['reason'] = f'keydown type={value} not supported'
                return base_result

            else:
                base_result['status'] = 'skipped'
                base_result['reason'] = f'unknown event type: {event_type}'
                return base_result

        except Exception as e:
            base_result['status'] = 'failed'
            base_result['error'] = str(e)[:200]
            return base_result

    def _try_click(self, selectors: List[str], text: str, result: Dict) -> Dict:
        """Try clicking using fallback selectors."""
        for sel in selectors:
            if not sel:
                continue
            try:
                if ':has-text(' in sel:
                    actual_text = sel.split(':has-text("')[1].split('")')[0]
                    page = self._cli._ensure_browser()
                    page.get_by_text(actual_text, exact=False).first.click(timeout=3000)
                elif sel.startswith('xpath='):
                    page = self._cli._ensure_browser()
                    page.locator(sel).first.click(timeout=3000)
                elif sel.startswith('//'):
                    page = self._cli._ensure_browser()
                    page.locator(f'xpath={sel}').first.click(timeout=3000)
                else:
                    self._cli.click(sel, timeout=3000)
                self._cli.wait_for_timeout(500)
                result['status'] = 'passed'
                result['used_selector'] = sel
                return result
            except Exception:
                continue

        if text:
            try:
                page = self._cli._ensure_browser()
                page.get_by_text(text, exact=False).first.click(timeout=3000)
                self._cli.wait_for_timeout(500)
                result['status'] = 'passed'
                result['used_selector'] = f'text="{text}"'
                return result
            except Exception:
                pass

        result['status'] = 'failed'
        result['error'] = f'No selector worked. Tried: {selectors[:3]}, text="{text}"'
        return result

    def _try_fill(self, selectors: List[str], value: str, result: Dict) -> Dict:
        """Try filling input with fallback selectors."""
        if value is None:
            result['status'] = 'skipped'
            result['reason'] = 'no value to fill'
            return result
        for sel in selectors:
            if not sel:
                continue
            try:
                self._cli.fill(sel, value, timeout=3000)
                self._cli.wait_for_timeout(300)
                result['status'] = 'passed'
                result['used_selector'] = sel
                return result
            except Exception:
                continue
        result['status'] = 'failed'
        result['error'] = f'No selector worked for fill. Tried: {selectors[:3]}'
        return result

    def _try_select(self, selectors: List[str], value: str, result: Dict) -> Dict:
        """Try selecting dropdown option with fallback selectors."""
        if value is None:
            result['status'] = 'skipped'
            result['reason'] = 'no value to select'
            return result
        for sel in selectors:
            if not sel:
                continue
            try:
                self._cli.select(sel, value=value, timeout=3000)
                self._cli.wait_for_timeout(300)
                result['status'] = 'passed'
                result['used_selector'] = sel
                return result
            except Exception:
                continue
        result['status'] = 'failed'
        result['error'] = f'No selector worked for select. Tried: {selectors[:3]}'
        return result


class CodeGenerator:
    """
    Generates a Python PlaywrightCLI test script from a recording JSON.

    Usage:
        CodeGenerator.generate('test_output/recording.json', 'test_output/test_script.py')
    """

    @staticmethod
    def generate(recording_path: str, output_path: str,
                 base_url: str = "http://localhost:3004",
                 test_name: str = None):
        """
        Generate a Python test script from a recording.

        Args:
            recording_path: Path to recording JSON.
            output_path: Path where the generated .py script will be saved.
            base_url: Base URL for authenticated_navigate.
            test_name: Name of the test (default: derived from filename).
        """
        with open(recording_path, 'r', encoding='utf-8') as f:
            recording = json.load(f)

        metadata = recording.get('metadata', {})
        events = recording.get('events', [])

        if test_name is None:
            test_name = os.path.splitext(os.path.basename(recording_path))[0]

        lines = []
        lines.append('"""')
        lines.append(f'Auto-generated E2E test from recording: {recording_path}')
        lines.append(f'')
        lines.append(f'Recorded at: {metadata.get("recorded_at", "unknown")}')
        lines.append(f'Events: {len(events)}')
        lines.append(f'Duration: {metadata.get("duration_ms", 0):.0f}ms')
        lines.append(f'')
        lines.append(f'Generated by CodeGenerator on {datetime.now().isoformat()}')
        lines.append('"""')
        lines.append('')
        lines.append('import sys')
        lines.append('import os')
        lines.append('')
        lines.append("sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'test_helpers'))")
        lines.append('from browser_auth_cli import PlaywrightCLI')
        lines.append('')
        lines.append('')
        lines.append(f'def test_{test_name}():')
        lines.append(f'    """')
        lines.append(f'    Recorded test: {test_name}')
        lines.append(f'    Auto-generated from manual E2E session.')
        lines.append(f'    """')
        lines.append(f"    cli = PlaywrightCLI(headless=True)")
        lines.append(f'')
        lines.append(f'    try:')

        seen_nav = False
        action_count = 0

        for event in events:
            event_type = event.get('type')
            target = event.get('target', {})
            selector = target.get('selector', '')
            text = target.get('text', '').replace('"', '\\"')
            value = event.get('value')

            if event_type == 'navigate':
                if not seen_nav:
                    target_path = value or '/'
                    lines.append(f'        # Navigate to {target_path}')
                    if target_path != '/':
                        lines.append(f"        cli.authenticated_navigate(")
                        lines.append(f"            '{target_path}',")
                        lines.append(f"            base_url='{base_url}',")
                        lines.append(f"            wait_for_selector='.el-table, .el-form, #app'")
                        lines.append(f"        )")
                    else:
                        lines.append(f"        cli.authenticated_navigate('/')")
                    seen_nav = True
                else:
                    target_path = value or '/'
                    lines.append(f'')
                    lines.append(f'        # Navigate to {target_path}')
                    lines.append(f"        cli.authenticated_navigate(")
                    lines.append(f"            '{target_path}',")
                    lines.append(f"            base_url='{base_url}',")
                    lines.append(f"            wait_for_selector='.el-table, .el-form, #app'")
                    lines.append(f"        )")

            elif event_type == 'click':
                action_count += 1
                safe_sel = selector.replace('"', '\\"')
                lines.append(f'')
                lines.append(f'        # Step {action_count}: click {text or selector[:60]}')
                if ':has-text(' in selector:
                    actual_text = selector.split(':has-text("')[1].split('")')[0]
                    lines.append(f'        cli.click(".el-button:has-text(\\"{actual_text}\\")", wait_after=500)')
                elif selector.startswith('xpath='):
                    lines.append(f'        cli.click("{safe_sel}", wait_after=500)')
                else:
                    lines.append(f'        cli.click("{safe_sel}", wait_after=500)')

            elif event_type == 'dblclick':
                action_count += 1
                lines.append(f'')
                lines.append(f'        # Step {action_count}: dblclick {text or selector[:60]}')
                lines.append(f'        cli.click("{selector}", wait_after=300)')
                lines.append(f'        cli.evaluate("document.querySelector(\\\\"{selector}\\\\").dispatchEvent(new MouseEvent(\\\\"dblclick\\\\", {{ bubbles: true }}))")')
                lines.append(f'        cli.wait_for_timeout(500)')

            elif event_type == 'input':
                action_count += 1
                safe_val = (value or '').replace('"', '\\"')
                lines.append(f'')
                lines.append(f'        # Step {action_count}: input "{safe_val[:40]}" into {selector[:60]}')
                lines.append(f'        cli.fill("{selector}", "{safe_val}")')

            elif event_type == 'select':
                action_count += 1
                safe_val = (value or '').replace('"', '\\"')
                lines.append(f'')
                lines.append(f'        # Step {action_count}: select "{safe_val}" in {selector[:60]}')
                lines.append(f'        cli.select("{selector}", value="{safe_val}")')

            elif event_type == 'check':
                action_count += 1
                lines.append(f'')
                lines.append(f'        # Step {action_count}: check {text or selector[:60]}')
                lines.append(f'        cli.click("{selector}", wait_after=500)')

            elif event_type == 'toggle':
                action_count += 1
                lines.append(f'')
                lines.append(f'        # Step {action_count}: toggle {text or selector[:60]}')
                lines.append(f'        cli.click("{selector}", wait_after=500)')

            elif event_type == 'keydown':
                if value == 'Enter':
                    lines.append(f'')
                    lines.append(f'        # Press Enter')
                    lines.append(f'        cli.evaluate("document.activeElement.dispatchEvent(new KeyboardEvent(\\\\"keydown\\\\", {{ key: \\\\"Enter\\\\", bubbles: true }}))")')
                elif value == 'Escape':
                    lines.append(f'')
                    lines.append(f'        # Press Escape')
                    lines.append(f'        cli.evaluate("document.dispatchEvent(new KeyboardEvent(\\\\"keydown\\\\", {{ key: \\\\"Escape\\\\", bubbles: true }}))")')

            if action_count > 0 and action_count % 3 == 0:
                lines.append(f'        cli.wait_for_stable(5000)')

        lines.append(f'')
        lines.append(f'        # Verify no errors')
        lines.append(f"        health = cli.check_health()")
        lines.append(f"        assert health['healthy'], f\"Page unhealthy: {{health['summary']}}\"")
        lines.append(f'')
        lines.append(f'        print("[PASS] {test_name}")')
        lines.append(f'        return True')
        lines.append(f'')
        lines.append(f'    except Exception as e:')
        lines.append(f'        print(f"[FAIL] {test_name}: {{e}}")')
        lines.append(f'        cli.screenshot("test_output/{test_name}_failure.png")')
        lines.append(f'        return False')
        lines.append(f'')
        lines.append(f'    finally:')
        lines.append(f'        cli.close()')
        lines.append(f'')
        lines.append(f'')
        lines.append(f'if __name__ == "__main__":')
        lines.append(f'    success = test_{test_name}()')
        lines.append(f'    sys.exit(0 if success else 1)')
        lines.append('')

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"[CODEGEN] Generated test script: {output_path} "
              f"({len(events)} events, {action_count} actions)")


def record_interactive(
    target_path: str = "/",
    output_path: str = "test_output/recording.json",
    headless: bool = False
) -> str:
    """
    Convenience function for interactive recording.

    Opens browser, navigates, records until user presses Enter in console.

    Args:
        target_path: Initial navigation target path.
        output_path: Where to save the recording JSON.
        headless: If True, headless mode. Usually False for recording.

    Returns:
        Path to the saved recording JSON.
    """
    rec = Recorder(headless=headless)
    rec.authenticated_navigate(
        target_path,
        wait_for_selector='.el-table, .el-form, .el-select, #app'
    )
    rec.start_recording()
    print(f"\n{'='*60}")
    print(f"  [RECORDER] Recording started on {target_path}")
    print(f"  Browser is open. Perform your manual E2E test steps.")
    print(f"  Press Enter in this console when done.")
    print(f"{'='*60}\n")
    input()
    rec.stop_recording(output_path)
    rec.close()
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python recorder.py record <target_path> [output_path]")
        print("  python recorder.py replay <recording.json>")
        print("  python recorder.py codegen <recording.json> [output.py]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'record':
        target = sys.argv[2] if len(sys.argv) > 2 else '/'
        output = sys.argv[3] if len(sys.argv) > 3 else 'test_output/recording.json'
        record_interactive(target, output)

    elif cmd == 'replay':
        rec_path = sys.argv[2]
        engine = ReplayEngine(rec_path, headless=False, fast_forward=True)
        results = engine.run()
        print(f"\nResults: {results['passed']}/{results['total']} passed, "
              f"{results['failed']} failed, {results['skipped']} skipped")
        for r in results.get('results', []):
            status = r.get('status', '?')
            if status != 'passed':
                print(f"  [#{r.get('seq')}] {status}: {r.get('type')} "
                      f"-> {r.get('selector','')[:60]} "
                      f"{r.get('error', '')[:80]}")

    elif cmd == 'codegen':
        rec_path = sys.argv[2]
        output = sys.argv[3] if len(sys.argv) > 3 else 'test_output/generated_test.py'
        CodeGenerator.generate(rec_path, output)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
