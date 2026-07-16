"""
Test: mermaid 11.13.0 escape syntax verification using Playwright
Uses CDN mermaid, no backend needed
"""
import sys
import json
import time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    with PlaywrightCLI() as cli:
        # Access the underlying Playwright page directly
        cli._ensure_browser()
        page = cli._page

        # Set HTML content with mermaid from CDN
        page.set_content("""<!DOCTYPE html>
<html><head>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.13.0/dist/mermaid.min.js"></script>
</head><body>
<div id="results"></div>
<div id="test-container" style="display:none"></div>
<script>
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });
window.__testDone = false;
window.__testResults = [];

(async () => {
  const tests = [
    { name: 'G1: pure Chinese', code: 'flowchart LR\\n  A["财务云"]' },
    { name: 'G2: #quot;', code: 'flowchart LR\\n  A["test#quot;name"]' },
    { name: 'G3: #91; #93;', code: 'flowchart LR\\n  A["test#91;1#93;"]' },

    { name: 'B1: #60; <', code: 'flowchart LR\\n  A["test#60;name"]' },
    { name: 'B2: #62; >', code: 'flowchart LR\\n  A["test#62;name"]' },
    { name: 'B3: #38; &', code: 'flowchart LR\\n  A["test#38;name"]' },

    { name: 'B4: #lt; <', code: 'flowchart LR\\n  A["test#lt;name"]' },
    { name: 'B5: #gt; >', code: 'flowchart LR\\n  A["test#gt;name"]' },
    { name: 'B6: #amp; &', code: 'flowchart LR\\n  A["test#amp;name"]' },

    { name: 'A1: &lt; direct', code: 'flowchart LR\\n  A["test&lt;name"]' },
    { name: 'A2: &gt; direct', code: 'flowchart LR\\n  A["test&gt;name"]' },
    { name: 'A3: &amp; direct', code: 'flowchart LR\\n  A["test&amp;name"]' },

    { name: 'F1: <br/>', code: 'flowchart LR\\n  A["hello<br/>world"]' },

    { name: 'H1: BOSS<系统> #lt;', code: 'flowchart LR\\n  A["BOSS#lt;系统#gt;"]' },
    { name: 'H2: A&B #38;', code: 'flowchart LR\\n  A["A#38;B"]' },

    { name: 'S1: subgraph #lt;', code: 'flowchart LR\\n  subgraph S1["test#lt;name"]\\n    A\\n  end' },
    { name: 'S2: subgraph #quot;', code: 'flowchart LR\\n  subgraph S1["test#quot;name"]\\n    A\\n  end' },

    { name: 'L1: -->|"label"| #60;', code: 'flowchart LR\\n  A -->|"test#60;name"| B' },
    { name: 'L2: <-- text --> #60;', code: 'flowchart LR\\n  A <-- test#60;name --> B' },

    // innerHTML injection simulation
    { name: 'I1: innerHTML+&lt;', code: 'flowchart LR\\n  A["test&lt;name"]', inject: 'innerHTML' },
    { name: 'I2: innerHTML+#60;', code: 'flowchart LR\\n  A["test#60;name"]', inject: 'innerHTML' },
    { name: 'I3: innerHTML+#lt;', code: 'flowchart LR\\n  A["test#lt;name"]', inject: 'innerHTML' },
    { name: 'I4: innerHTML+<br/>', code: 'flowchart LR\\n  A["hello<br/>world"]', inject: 'innerHTML' },
    { name: 'I5: innerHTML+BOSS&lt;系统&gt;', code: 'flowchart LR\\n  A["BOSS&lt;系统&gt;"]', inject: 'innerHTML' },

    // textContent injection simulation
    { name: 'T1: textContent+&lt;', code: 'flowchart LR\\n  A["test&lt;name"]', inject: 'textContent' },
    { name: 'T2: textContent+#60;', code: 'flowchart LR\\n  A["test#60;name"]', inject: 'textContent' },
    { name: 'T3: textContent+#lt;', code: 'flowchart LR\\n  A["test#lt;name"]', inject: 'textContent' },
    { name: 'T4: textContent+<br/>', code: 'flowchart LR\\n  A["hello<br/>world"]', inject: 'textContent' },
  ];

  const results = [];
  const container = document.getElementById('test-container');

  for (const test of tests) {
    try {
      let codeToRender = test.code;

      if (test.inject === 'innerHTML') {
        container.innerHTML = '<pre class="mermaid">' + test.code + '</pre>';
        const el = container.querySelector('.mermaid');
        codeToRender = el.textContent;
        container.innerHTML = '';
      } else if (test.inject === 'textContent') {
        container.innerHTML = '';
        const pre = document.createElement('pre');
        pre.className = 'mermaid';
        pre.textContent = test.code;
        container.appendChild(pre);
        codeToRender = pre.textContent;
        container.innerHTML = '';
      }

      const { svg } = await mermaid.render('svg' + Date.now() + Math.floor(Math.random() * 99999), codeToRender);
      let detail = '';
      if (test.inject) {
        detail = test.inject + ' tc: "' + codeToRender.substring(0, 50) + '"';
      } else {
        detail = 'svg ' + svg.length + ' chars';
      }
      results.push({ name: test.name, result: 'PASS', detail });
    } catch (err) {
      results.push({ name: test.name, result: 'FAIL', detail: (err.message || String(err)).substring(0, 120) });
    }
  }

  window.__testResults = results;
  window.__testDone = true;
})();
</script>
</body></html>""", wait_until="networkidle")

        # Wait for tests to complete
        for _ in range(30):
            done = page.evaluate('window.__testDone')
            if done:
                break
            time.sleep(1)

        results = page.evaluate('window.__testResults')

        pass_count = 0
        fail_count = 0
        for r in results:
            status = r['result']
            if status == 'PASS':
                pass_count += 1
                print(f'[PASS] {r["name"]}: {r["detail"]}')
            else:
                fail_count += 1
                print(f'[FAIL] {r["name"]}: {r["detail"]}')

        print(f'\n=== Results: {pass_count}/{pass_count + fail_count} PASS, {fail_count} FAIL ===')


if __name__ == '__main__':
    main()
