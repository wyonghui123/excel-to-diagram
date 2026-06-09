"""Frontend E2E sort test: user list page updated_at sorting"""
import sys, os, time, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True)
passed = True

try:
    print("[1] Navigating to user-permission page...")
    cli.authenticated_navigate(
        '/user-permission/users',
        wait_for_selector='.el-table__body-wrapper',
        timeout=20000
    )
    
    cli.wait_for_selector('.el-table__row', timeout=15000)
    cli.wait_for_stable(max_wait=5000, stable_window=1000)
    
    # Check for errors
    errors = cli.assert_no_errors()
    print(f"    Page errors: {errors['ok']}")
    
    # Get column headers to find updated_at column
    headers = cli.evaluate("""
        () => {
            const headers = document.querySelectorAll('.el-table__header-wrapper th');
            return Array.from(headers).map((th, i) => ({
                index: i,
                text: th.textContent?.trim() || '',
                className: th.className || ''
            }));
        }
    """)
    
    # Find the updated_at / 变更时间 column
    updated_at_index = None
    for h in headers:
        print(f"    col[{h['index']}] '{h['text']}' sortable={'is-sortable' in h['className']}")
        if '变更时间' in h['text'] or '更新时间' in h['text'] or 'updated_at' in h['text'].lower():
            updated_at_index = h['index']
    
    if updated_at_index is None:
        print("\n[ERROR] Could not find '变更时间' column!")
        passed = False
    else:
        print(f"\n    Found 变更时间 at column index {updated_at_index}")
        
        # Helper: extract updated_at values + get header aria-sort
        def get_sort_state():
            return cli.evaluate(f"""
                () => {{
                    const th = document.querySelectorAll('.el-table__header-wrapper th')[{updated_at_index}];
                    if (!th) return {{ error: 'th not found' }};
                    const rows = document.querySelectorAll('.el-table__body-wrapper .el-table__row');
                    const values = Array.from(rows).map(row => {{
                        const cells = row.querySelectorAll('.el-table__cell');
                        const cell = cells[{updated_at_index}];
                        return cell ? cell.textContent?.trim() || '' : '';
                    }});
                    return {{
                        ariaSort: th.getAttribute('aria-sort'),
                        className: th.className,
                        values: values
                    }};
                }}
            """)
        
        def js_click_sort_header():
            """Use JS click on th element directly (bypasses Playwright click interception issues)"""
            return cli.evaluate(f"""
                () => {{
                    const th = document.querySelectorAll('.el-table__header-wrapper th')[{updated_at_index}];
                    if (th) {{
                        th.click();
                        return 'clicked';
                    }}
                    return 'NOT FOUND';
                }}
            """)
        
        def verify_sorted(values, direction):
            """Verify values are sorted in given direction (asc/desc)"""
            non_empty = [v for v in values if v]
            if len(non_empty) < 2:
                return True
            if direction == 'desc':
                return all(non_empty[i] >= non_empty[i+1] for i in range(len(non_empty)-1))
            else:
                return all(non_empty[i] <= non_empty[i+1] for i in range(len(non_empty)-1))
        
        # Step 1: Initial state
        state = get_sort_state()
        print(f"\n[2] Initial state: aria-sort={state.get('ariaSort')}")
        print(f"    First 3 values: {state['values'][:3]}")
        
        # Step 2: Click to cycle through sort states
        # Element Plus sort cycle: null → ascending → descending → null
        # Initial is 'descending' (defaultSort), so:
        # Click 1: descending → null (clear)
        # Click 2: null → ascending
        # Click 3: ascending → descending
        
        results = []
        
        for click_num, expected_dir in enumerate(['null', 'asc', 'desc']):
            print(f"\n[3.{click_num}] Click #{click_num+1} (expecting {expected_dir})...")
            js_click_sort_header()
            cli.wait_for_stable(max_wait=3000, stable_window=1000)
            
            state = get_sort_state()
            aria = state.get('ariaSort')
            vals = state['values']
            print(f"    aria-sort={aria}, first 3: {vals[:3]}")
            
            if aria == 'ascending':
                ok = verify_sorted(vals, 'asc')
            elif aria == 'descending':
                ok = verify_sorted(vals, 'desc')
            else:
                # null sort: should have default ordering (desc by updated_at)
                ok = verify_sorted(vals, 'desc')
            
            results.append((expected_dir, aria, ok))
            print(f"    Sorted correctly: {ok}")
        
        # Summary
        print(f"\n{'='*50}")
        all_ok = all(r[2] for r in results)
        if all_ok:
            print("ALL FRONTEND SORT TESTS PASSED")
        else:
            print("FRONTEND SORT TESTS FAILED:")
            for expected, actual, ok in results:
                status = "PASS" if ok else "FAIL"
                print(f"  expected={expected}, actual={actual}: {status}")
            passed = False

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    passed = False

finally:
    cli.close()
    sys.exit(0 if passed else 1)
