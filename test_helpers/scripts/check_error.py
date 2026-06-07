"""检查 vite error overlay"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time


def main():
    cli = PlaywrightCLI()
    try:
        cli.goto('http://localhost:3004', wait_until='networkidle')
        time.sleep(3)
        overlay = cli.evaluate("""
            () => {
                const o = document.querySelector('vite-error-overlay');
                if (!o) return null;
                const sr = o.shadowRoot;
                if (!sr) return null;
                const m = sr.querySelector('.message-body');
                const f = sr.querySelector('.file');
                const fr = sr.querySelector('pre.frame');
                return {
                    msg: m?.textContent,
                    file: f?.textContent,
                    frame: fr?.textContent
                };
            }
        """)
        print(f"[error] {overlay}")
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        cli.close()


if __name__ == "__main__":
    main()
