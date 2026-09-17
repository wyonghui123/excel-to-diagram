#!/usr/bin/env python3
"""
verify_deploy.py - End-to-end deployment verification via Playwright
========================================================================
用途: 用 Playwright 实际访问远端, 截图, 验证部署后真实状态
设计: 不依赖命令行, 直接浏览器验证
用法:
  python tools/verify_deploy.py --host 172.20.59.7 --frontend-port 8081 --backend-port 5001
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Playwright (assumed available)
try:
    from playwright.sync_api import sync_playwright, Page, Browser
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright", file=sys.stderr)
    sys.exit(1)


class Verifier:
    def __init__(self, host: str, frontend_port: int, backend_port: int, screenshots_dir: Path):
        self.host = host
        self.frontend_port = frontend_port
        self.backend_port = backend_port
        self.screenshots_dir = screenshots_dir
        self.screenshots_dir.mkdir(exist_ok=True, parents=True)
        self.results: List[Dict] = []
        self.browser: Optional[Browser] = None

    def log(self, name: str, passed: bool, details: str = ""):
        """记录一个验证结果"""
        result = {
            "name": name,
            "passed": passed,
            "details": details,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.results.append(result)
        symbol = "✓" if passed else "✗"
        color = "\033[0;32m" if passed else "\033[0;31m"
        print(f"  {color}[{symbol}] {name}: {details}\033[0m")

    def url(self, port: int, path: str) -> str:
        return f"http://{self.host}:{port}{path}"

    def http_check(self, page: Page, name: str, url: str, expect_status: int = 200) -> bool:
        """用 page.goto 检查 URL"""
        try:
            resp = page.goto(url, timeout=10000, wait_until="domcontentloaded")
            status = resp.status if resp else 0
            passed = status == expect_status
            self.log(name, passed, f"GET {url} -> {status}")
            return passed
        except Exception as e:
            self.log(name, False, f"GET {url} -> ERROR: {str(e)[:100]}")
            return False

    def screenshot(self, page: Page, name: str) -> Path:
        """截图保存"""
        path = self.screenshots_dir / f"{name}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            return path
        except Exception as e:
            print(f"  [WARN] Screenshot failed for {name}: {e}")
            return path

    def verify(self):
        """主验证流程"""
        print("=" * 70)
        print(f"  DEPLOYMENT VERIFICATION (via Playwright)")
        print(f"  Host: {self.host}")
        print(f"  Frontend: {self.frontend_port}, Backend: {self.backend_port}")
        print(f"  Screenshots: {self.screenshots_dir}")
        print("=" * 70)

        with sync_playwright() as p:
            self.browser = p.chromium.launch(headless=True)
            context = self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
            page = context.new_page()

            # ===== Phase 1: HTTP 端点可达性 =====
            print("\n[Phase 1] HTTP Endpoint Reachability")
            self.http_check(
                page, "frontend_root",
                self.url(self.frontend_port, "/"),
            )
            self.http_check(
                page, "backend_health",
                self.url(self.backend_port, "/api/v1/health"),
            )
            self.http_check(
                page, "backend_users_me_unauth",
                self.url(self.backend_port, "/api/v1/users/me"),
                expect_status=401,  # 未登录期望 401
            )

            # ===== Phase 2: Login =====
            print("\n[Phase 2] Login Flow")
            try:
                page.goto(self.url(self.frontend_port, "/"), timeout=10000)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                self.screenshot(page, "01_login_page")

                # 尝试找用户名/密码输入框
                username_selectors = [
                    "input[name='username']",
                    "input[type='text']",
                    "input[placeholder*='用户']",
                    "input[placeholder*='账号']",
                ]
                password_selectors = [
                    "input[name='password']",
                    "input[type='password']",
                ]
                submit_selectors = [
                    "button[type='submit']",
                    "button:has-text('登录')",
                    "button:has-text('Login')",
                ]

                username_input = None
                for sel in username_selectors:
                    try:
                        if page.locator(sel).count() > 0:
                            username_input = page.locator(sel).first
                            break
                    except Exception:
                        pass

                password_input = None
                for sel in password_selectors:
                    try:
                        if page.locator(sel).count() > 0:
                            password_input = page.locator(sel).first
                            break
                    except Exception:
                        pass

                submit_btn = None
                for sel in submit_selectors:
                    try:
                        if page.locator(sel).count() > 0:
                            submit_btn = page.locator(sel).first
                            break
                    except Exception:
                        pass

                if username_input and password_input and submit_btn:
                    username_input.fill("admin")
                    password_input.fill("admin123")
                    self.screenshot(page, "02_login_filled")
                    submit_btn.click()
                    time.sleep(3)
                    self.screenshot(page, "03_after_login")

                    # 检查登录后 URL
                    current_url = page.url
                    logged_in = "/login" not in current_url and current_url != self.url(self.frontend_port, "/")
                    self.log("login_success", logged_in, f"Redirected to: {current_url}")
                else:
                    self.log("login_form_found", False,
                            f"Missing fields: username={username_input is not None}, "
                            f"password={password_input is not None}, "
                            f"submit={submit_btn is not None}")
            except Exception as e:
                self.log("login_flow", False, f"Exception: {str(e)[:200]}")

            # ===== Phase 3: API Endpoint Tests =====
            print("\n[Phase 3] API Endpoints (with auth if possible)")
            # 尝试登录拿 token
            token = None
            try:
                api_page = context.new_page()
                resp = api_page.request.post(
                    self.url(self.backend_port, "/api/v1/auth/login"),
                    data={"username": "admin", "password": "admin123"},
                    headers={"Content-Type": "application/json"},
                    timeout=10000,
                )
                if resp.ok:
                    data = resp.json()
                    token = data.get("data", {}).get("token", "")
                    self.log("api_login", bool(token), f"Token length: {len(token)}")
                else:
                    self.log("api_login", False, f"Status: {resp.status}, body: {resp.text()[:200]}")
            except Exception as e:
                self.log("api_login", False, f"Exception: {str(e)[:200]}")

            # 测 /api/v1/users/me (之前 500)
            if token:
                try:
                    resp = api_page.request.get(
                        self.url(self.backend_port, "/api/v1/users/me"),
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10000,
                    )
                    self.log("api_users_me", resp.ok, f"Status: {resp.status}, body: {resp.text()[:200]}")
                except Exception as e:
                    self.log("api_users_me", False, f"Exception: {str(e)[:200]}")

                # 测 /api/v2/action/user.authenticate (之前 500)
                try:
                    resp = api_page.request.post(
                        self.url(self.backend_port, "/api/v2/action/user.authenticate"),
                        data={"username": "admin", "password": "admin123"},
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        timeout=10000,
                    )
                    self.log("api_v2_action_authenticate", resp.ok, f"Status: {resp.status}, body: {resp.text()[:200]}")
                except Exception as e:
                    self.log("api_v2_action_authenticate", False, f"Exception: {str(e)[:200]}")

                # 测 enum-types (mutability 修复验证)
                try:
                    resp = api_page.request.get(
                        self.url(self.backend_port, "/api/v1/enum-types"),
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10000,
                    )
                    if resp.ok:
                        data = resp.json()
                        items = data.get("data", [])
                        # 收集 mutability 分布
                        from collections import Counter
                        mut_counter = Counter(e.get("mutability", "N/A") for e in items)
                        mut_str = ", ".join(f"{k}={v}" for k, v in mut_counter.items())
                        # 检查关键值
                        has_fullEditable = mut_counter.get("fullEditable", 0) > 0
                        has_fully_editable = mut_counter.get("fully_editable", 0) > 0
                        passed = has_fullEditable and not has_fully_editable
                        details = f"Total: {len(items)}, mutability: [{mut_str}]"
                        if has_fully_editable:
                            details += " (HAS DEPRECATED fully_editable! fix not applied)"
                        self.log("api_enum_types_mutability", passed, details)
                    else:
                        self.log("api_enum_types_mutability", False, f"Status: {resp.status}")
                except Exception as e:
                    self.log("api_enum_types_mutability", False, f"Exception: {str(e)[:200]}")

            # ===== Phase 4: Frontend UI Check =====
            print("\n[Phase 4] Frontend UI Check")
            try:
                page.goto(self.url(self.frontend_port, "/"), timeout=10000)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                self.screenshot(page, "04_frontend_home")

                # 检查页面内容
                body_text = page.text_content("body") or ""
                has_login_form = any(
                    kw in body_text.lower()
                    for kw in ["login", "登录", "sign in", "username", "密码"]
                )
                self.log("frontend_login_visible", has_login_form,
                        f"Body text length: {len(body_text)}, has login form: {has_login_form}")

                # 检查 console errors
                console_errors = []
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                time.sleep(2)
                self.log("frontend_no_console_errors", len(console_errors) == 0,
                        f"Console errors: {len(console_errors)}")
                if console_errors:
                    for err in console_errors[:3]:
                        print(f"    Console error: {err[:200]}")
            except Exception as e:
                self.log("frontend_ui", False, f"Exception: {str(e)[:200]}")

            self.browser.close()

        # ===== Report =====
        print("\n" + "=" * 70)
        print("  VERIFICATION SUMMARY")
        print("=" * 70)
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        print(f"  Passed: {passed}/{total}")
        if passed == total:
            print("\033[0;32m  ALL CHECKS PASSED ✓\033[0m")
        else:
            print("\033[0;31m  SOME CHECKS FAILED ✗\033[0m")
            print("\n  Failed checks:")
            for r in self.results:
                if not r["passed"]:
                    print(f"    - {r['name']}: {r['details']}")

        # 保存报告
        report_path = self.screenshots_dir / "report.json"
        report_path.write_text(json.dumps(self.results, indent=2, ensure_ascii=False))
        print(f"\n  Report: {report_path}")
        print(f"  Screenshots: {self.screenshots_dir}")

        return passed == total


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end deployment verification via Playwright"
    )
    parser.add_argument("--host", default="172.20.59.7", help="远端主机")
    parser.add_argument("--frontend-port", type=int, default=8081)
    parser.add_argument("--backend-port", type=int, default=5001)
    parser.add_argument("--screenshots", type=Path, default=Path("verify_screenshots"))
    args = parser.parse_args()

    verifier = Verifier(
        host=args.host,
        frontend_port=args.frontend_port,
        backend_port=args.backend_port,
        screenshots_dir=args.screenshots,
    )
    success = verifier.verify()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
