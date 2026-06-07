/**
 * Inject test helpers into the page.
 * This file is loaded by Python and its content is executed as page.evaluate().
 *
 * 两大核心能力：
 *   1. 突变可识别性 — 多层追踪（Store / DOM / Network / Event），精确知道什么变了
 *   2. 内容可验证性 — 多层一致性检查（Store↔DOM / API↔DOM / 错误检测），验证内容正确性
 */

(function() {
    window.__consoleErrors = window.__consoleErrors || []
    window.__consoleWarnings = window.__consoleWarnings || []

    var _origError = console.error
    console.error = function() {
        window.__consoleErrors.push({
            message: Array.from(arguments).map(function(a) {
                return String(a).substring(0, 300)
            }).join(' '),
            timestamp: Date.now()
        })
        return _origError.apply(console, arguments)
    }

    var _origWarn = console.warn
    console.warn = function() {
        window.__consoleWarnings.push({
            message: Array.from(arguments).map(function(a) {
                return String(a).substring(0, 300)
            }).join(' '),
            timestamp: Date.now()
        })
        return _origWarn.apply(console, arguments)
    }
})()

window.__test__ = (() => {
    const pinia = () => {
        const app = document.querySelector('#app')?.__vue_app__;
        return app?.config?.globalProperties?.$pinia;
    };

    const getStore = (name) => {
        const p = pinia();
        return p?._s?.get(name);
    };

    const serializeValue = (v) => {
        if (v === null || v === undefined) return v;
        if (typeof v === 'function') return '[Function]';
        if (v instanceof Map) return Object.fromEntries(v);
        if (v instanceof Set) return Array.from(v);
        if (Array.isArray(v)) return v.map(serializeValue);
        if (typeof v === 'object' && v.constructor?.name === 'RefImpl')
            return serializeValue(v.value ?? v._value);
        if (typeof v === 'object') {
            const o = {};
            for (const k of Object.keys(v)) {
                try { o[k] = serializeValue(v[k]); } catch(e) { o[k] = '[Error]'; }
            }
            return o;
        }
        return v;
    };

    // ============================================================
    // PART 1: 状态快照 & diff（已有，保留）
    // ============================================================

    const snapshot = () => {
        const p = pinia();
        if (!p) return { error: 'Pinia not found' };
        const stores = {};
        for (const [key, store] of p._s) {
            const state = {};
            for (const k of Object.keys(store.$state)) {
                try { state[k] = serializeValue(store.$state[k]); } catch(e) { state[k] = '[Error]'; }
            }
            stores[key] = state;
        }
        return { timestamp: Date.now(), stores };
    };

    const diff = (prev, curr) => {
        const changes = {};
        const prevStores = prev?.stores || {};
        const currStores = curr?.stores || {};
        const allKeys = new Set([...Object.keys(prevStores), ...Object.keys(currStores)]);
        for (const key of allKeys) {
            const prevState = prevStores[key] || {};
            const currState = currStores[key] || {};
            const storeChanges = {};
            for (const k of Object.keys(currState)) {
                if (JSON.stringify(prevState[k]) !== JSON.stringify(currState[k])) {
                    storeChanges[k] = { from: prevState[k], to: currState[k] };
                }
            }
            if (Object.keys(storeChanges).length > 0) changes[key] = storeChanges;
        }
        return { changed: Object.keys(changes).length > 0, changes };
    };

    // ============================================================
    // PART 1b: 增强型突变追踪 — 三层：Store + DOM + Network
    // ============================================================

    let _storeMutations = [];
    let _storeWatching = false;

    const startWatching = () => {
        if (_storeWatching) return 'already watching';
        const p = pinia();
        if (!p) return 'Pinia not found';
        _storeMutations = [];
        for (const [key, store] of p._s) {
            store.$subscribe((mutation, state) => {
                _storeMutations.push({
                    store: key,
                    type: mutation.type,
                    storeId: mutation.storeId,
                    events: mutation.events ? Object.keys(mutation.events) : [],
                    timestamp: Date.now()
                });
            });
        }
        _storeWatching = true;
        return 'watching ' + p._s.size + ' stores';
    };

    const getMutations = () => {
        const result = [..._storeMutations];
        _storeMutations = [];
        return result;
    };

    // ---- DOM Mutation Tracking (MutationObserver) ----

    let _domObserver = null;
    let _domMutations = [];
    let _domTracking = false;

    const startDOMTracking = (targetSelector) => {
        if (_domTracking) return 'already tracking DOM';
        _domMutations = [];
        let target = document.body;
        if (targetSelector) {
            const el = document.querySelector(targetSelector);
            if (el) target = el;
        }
        _domObserver = new MutationObserver((records) => {
            for (const record of records) {
                const summary = { timestamp: Date.now(), type: record.type };
                if (record.type === 'attributes') {
                    summary.attributeName = record.attributeName;
                    summary.target = _describeElement(record.target);
                    summary.oldValue = record.oldValue;
                } else if (record.type === 'characterData') {
                    summary.target = _describeElement(record.target.parentElement);
                    summary.oldValue = record.oldValue;
                } else if (record.type === 'childList') {
                    summary.addedCount = record.addedNodes.length;
                    summary.removedCount = record.removedNodes.length;
                    summary.added = Array.from(record.addedNodes)
                        .filter(n => n.nodeType === 1)
                        .slice(0, 5)
                        .map(n => _describeElement(n));
                    summary.removed = Array.from(record.removedNodes)
                        .filter(n => n.nodeType === 1)
                        .slice(0, 5)
                        .map(n => _describeElement(n));
                }
                _domMutations.push(summary);
            }
        });
        _domObserver.observe(target, {
            attributes: true,
            attributeOldValue: true,
            childList: true,
            subtree: true,
            characterData: true,
            characterDataOldValue: true
        });
        _domTracking = true;
        return 'tracking DOM on ' + (targetSelector || 'body');
    };

    const getDOMMutations = () => {
        if (!_domTracking) return [];
        const result = [..._domMutations];
        _domMutations = [];
        return result;
    };

    const stopDOMTracking = () => {
        if (_domObserver) {
            _domObserver.disconnect();
            _domObserver = null;
        }
        _domTracking = false;
        return 'stopped';
    };

    const _describeElement = (el) => {
        if (!el || el.nodeType !== 1) return '#' + (el?.nodeType || 'text');
        const tag = el.tagName.toLowerCase();
        const id = el.id ? '#' + el.id : '';
        const cls = el.className && typeof el.className === 'string'
            ? '.' + el.className.split(' ').filter(c => c).slice(0, 3).join('.')
            : '';
        const text = el.textContent ? el.textContent.trim().slice(0, 40) : '';
        return tag + id + cls + (text ? ' "' + text + '"' : '');
    };

    // ---- Network Request Tracking (fetch + XHR interception) ----

    let _networkRequests = [];
    let _networkTracking = false;
    let _pendingRequests = 0;

    const startNetworkTracking = () => {
        if (_networkTracking) return 'already tracking network';
        _networkRequests = [];
        _pendingRequests = 0;

        const origFetch = window.fetch;
        window.fetch = function(...args) {
            const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || 'unknown';
            const method = (args[1]?.method || 'GET').toUpperCase();
            const startTime = Date.now();
            _pendingRequests++;
            const entry = { url, method, startTime, status: 'pending' };
            _networkRequests.push(entry);
            return origFetch.apply(this, args).then(resp => {
                entry.status = resp.status;
                entry.duration = Date.now() - startTime;
                _pendingRequests--;
                return resp.clone();
            }).catch(err => {
                entry.status = 'error';
                entry.error = err.message;
                entry.duration = Date.now() - startTime;
                _pendingRequests--;
                throw err;
            });
        };

        const origXHROpen = XMLHttpRequest.prototype.open;
        const origXHRSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(method, url) {
            this.__test_method = method;
            this.__test_url = url;
            this.__test_start = Date.now();
            return origXHROpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function() {
            _pendingRequests++;
            const entry = {
                url: this.__test_url,
                method: this.__test_method || 'GET',
                startTime: this.__test_start,
                status: 'pending'
            };
            _networkRequests.push(entry);
            this.addEventListener('loadend', () => {
                entry.status = this.status;
                entry.duration = Date.now() - entry.startTime;
                _pendingRequests--;
            });
            this.addEventListener('error', () => {
                entry.status = 'error';
                entry.duration = Date.now() - entry.startTime;
                _pendingRequests--;
            });
            return origXHRSend.apply(this, arguments);
        };

        _networkTracking = true;
        return 'network tracking started';
    };

    const getNetworkRequests = () => {
        const result = [..._networkRequests];
        _networkRequests = [];
        return result;
    };

    const getPendingRequests = () => _pendingRequests;

    const stopNetworkTracking = () => {
        _networkTracking = false;
        return 'network tracking stopped';
    };

    // ---- All-in-one tracking ----

    const startAllTracking = (targetSelector) => {
        const results = {
            store: startWatching(),
            dom: startDOMTracking(targetSelector),
            network: startNetworkTracking()
        };
        return results;
    };

    const getAllChanges = () => {
        return {
            timestamp: Date.now(),
            store: getMutations(),
            dom: getDOMMutations(),
            network: getNetworkRequests(),
            pendingRequests: getPendingRequests()
        };
    };

    // ---- Wait for stability ----

    const waitForStable = (maxWait = 10000, stableWindow = 500) => {
        return new Promise((resolve, reject) => {
            const start = Date.now();
            let lastChange = Date.now();
            const check = () => {
                const now = Date.now();
                const pending = _pendingRequests || 0;
                if (pending > 0) {
                    lastChange = now;
                }
                if (now - lastChange >= stableWindow) {
                    resolve({
                        stable: true,
                        waited: now - start,
                        storeMutations: _storeMutations.length,
                        domMutations: _domMutations.length,
                        networkRequests: _networkRequests.length,
                        pendingRequests: pending
                    });
                    return;
                }
                if (now - start > maxWait) {
                    resolve({
                        stable: false,
                        waited: maxWait,
                        reason: 'timeout',
                        storeMutations: _storeMutations.length,
                        domMutations: _domMutations.length,
                        networkRequests: _networkRequests.length,
                        pendingRequests: pending
                    });
                    return;
                }
                setTimeout(check, 100);
            };
            check();
        });
    };

    // ============================================================
    // PART 2: 内容可验证性 — 多层一致性检查
    // ============================================================

    // ---- Store-DOM 一致性 ----

    const verifyTableConsistency = (storeName, tableSelector) => {
        const store = getStore(storeName);
        const table = document.querySelector(tableSelector);
        if (!table) return { ok: false, error: 'Table not found: ' + tableSelector };

        const rows = table.querySelectorAll('tbody tr, .el-table__body tr');
        const storeItems = store?.items || store?.list || store?.data || [];

        const result = {
            ok: true,
            domRowCount: rows.length,
            storeItemCount: Array.isArray(storeItems) ? storeItems.length : 'N/A',
            checks: {}
        };

        if (Array.isArray(storeItems)) {
            result.checks.rowCountMatch = rows.length === storeItems.length;
            if (!result.checks.rowCountMatch) {
                result.ok = false;
                result.error = `Row count mismatch: DOM=${rows.length}, Store=${storeItems.length}`;
            }
        }

        // 检查分页信息
        if (store?.pagination) {
            result.checks.hasPagination = true;
            result.storeTotal = store.pagination.total || store.total;
        }

        // 检查 loading 状态
        if (store?.loading !== undefined) {
            result.checks.storeLoading = store.loading;
            const loadingEl = table.querySelector('.el-loading-mask, .el-table__empty-block');
            result.checks.domLoading = !!loadingEl;
        }

        return result;
    };

    const verifyFormConsistency = (storeName, formSelector) => {
        const store = getStore(storeName);
        const form = document.querySelector(formSelector);
        if (!form) return { ok: false, error: 'Form not found: ' + formSelector };

        const formData = store?.formData || store?.currentItem || {};
        const inputs = form.querySelectorAll('input, select, textarea');
        const mismatches = [];

        for (const input of inputs) {
            const name = input.name || input.getAttribute('data-field');
            if (!name) continue;
            const domValue = input.type === 'checkbox' ? input.checked : input.value;
            const storeValue = formData[name];
            if (storeValue !== undefined && String(domValue) !== String(storeValue)) {
                mismatches.push({
                    field: name,
                    dom: domValue,
                    store: storeValue
                });
            }
        }

        return {
            ok: mismatches.length === 0,
            totalFields: inputs.length,
            mismatches,
            storeKeys: Object.keys(formData)
        };
    };

    // ---- 错误/边界状态检测 ----

    const detectErrorStates = () => {
        const errors = [];

        const errorMessages = document.querySelectorAll(
            '.el-message--error, .el-alert--error, .el-notification--error, ' +
            '[class*="error-message"], [class*="errorMessage"], ' +
            '.el-form-item__error, .el-table__empty-block'
        );
        for (const el of errorMessages) {
            const text = el.textContent.trim();
            if (text) errors.push({ type: 'error', text, element: _describeElement(el) });
        }

        const warningMessages = document.querySelectorAll(
            '.el-message--warning, .el-alert--warning, .el-notification--warning'
        );
        for (const el of warningMessages) {
            const text = el.textContent.trim();
            if (text) errors.push({ type: 'warning', text, element: _describeElement(el) });
        }

        const loadingSpinners = document.querySelectorAll(
            '.el-loading-mask:not([style*="display: none"])'
        );
        for (const el of loadingSpinners) {
            errors.push({ type: 'loading', element: _describeElement(el.closest('[class]') || el) });
        }

        const emptyStates = document.querySelectorAll('.el-empty, .el-table__empty-text');
        for (const el of emptyStates) {
            const text = el.textContent.trim();
            errors.push({ type: 'empty', text, element: _describeElement(el) });
        }

        // 检查 disabled 状态
        const disabledButtons = document.querySelectorAll(
            '.el-button.is-disabled, button[disabled]'
        );
        if (disabledButtons.length > 0) {
            errors.push({
                type: 'disabled',
                count: disabledButtons.length,
                buttons: Array.from(disabledButtons).slice(0, 5).map(b => b.textContent.trim())
            });
        }

        return {
            hasErrors: errors.some(e => e.type === 'error'),
            hasWarnings: errors.some(e => e.type === 'warning'),
            hasLoading: errors.some(e => e.type === 'loading'),
            hasEmpty: errors.some(e => e.type === 'empty'),
            items: errors
        };
    };

    // ---- 结构化内容验证 ----

    const verifyTableData = (tableSelector, expectedData) => {
        const table = document.querySelector(tableSelector);
        if (!table) return { ok: false, error: 'Table not found: ' + tableSelector };

        const headers = Array.from(
            table.querySelectorAll('thead th, .el-table__header th')
        ).map(h => h.textContent.trim());

        const rows = Array.from(
            table.querySelectorAll('tbody tr, .el-table__body tr')
        ).map(row =>
            Array.from(row.querySelectorAll('td')).map(d => d.textContent.trim())
        );

        const result = {
            ok: true,
            headers,
            rowCount: rows.length,
            rows: rows.slice(0, 10),
            checks: {}
        };

        if (expectedData) {
            if (expectedData.rowCount !== undefined) {
                result.checks.rowCount = rows.length === expectedData.rowCount;
                if (!result.checks.rowCount) result.ok = false;
            }
            if (expectedData.headers) {
                const missingHeaders = expectedData.headers.filter(h => !headers.includes(h));
                result.checks.headers = missingHeaders.length === 0;
                if (!result.checks.headers) {
                    result.missingHeaders = missingHeaders;
                    result.ok = false;
                }
            }
            if (expectedData.cellContains) {
                const found = rows.some(row =>
                    row.some(cell => cell.includes(expectedData.cellContains))
                );
                result.checks.cellContains = found;
                if (!found) result.ok = false;
            }
        }

        return result;
    };

    const verifyPageStructure = (expectedSelectors) => {
        const results = {};
        let allOk = true;
        for (const sel of expectedSelectors) {
            const el = document.querySelector(sel);
            const isVisible = el && el.offsetHeight > 0;
            results[sel] = { found: !!el, visible: isVisible };
            if (!isVisible) allOk = false;
        }
        return { ok: allOk, elements: results };
    };

    // ---- 节点可见性（非 DOM 存在） ----

    const getVisibleTextNodes = (text) => {
        const all = document.querySelectorAll('*');
        const results = [];
        for (const el of all) {
            if (el.children.length === 0 && (el.textContent || '').trim() === text) {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                const isVisible = (
                    rect.width > 0 && rect.height > 0 &&
                    style.display !== 'none' && style.visibility !== 'hidden' &&
                    parseFloat(style.opacity) > 0.01 &&
                    rect.x >= 0 && rect.y >= 0 &&
                    rect.x + rect.width <= innerWidth &&
                    rect.y + rect.height <= innerHeight
                );
                if (isVisible) {
                    results.push({
                        tag: el.tagName,
                        class: String(el.className).slice(0, 60),
                        rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                    });
                }
            }
        }
        return results;
    };

    // ============================================================
    // PART 3: 原有方法（保留兼容）
    // ============================================================

    const getComponentState = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return { found: false, selector };
        const vue = el.__vueParentComponent;
        if (!vue) return { found: true, hasVue: false };
        const props = {};
        if (vue.props) {
            for (const k of Object.keys(vue.props)) {
                try { props[k] = serializeValue(vue.props[k]); } catch(e) { props[k] = '[Error]'; }
            }
        }
        return { found: true, hasVue: true, props };
    };

    const assertTable = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return { found: false, error: 'Table not found: ' + selector };
        const rows = el.querySelectorAll('tbody tr, .el-table__body tr');
        const headers = el.querySelectorAll('thead th, .el-table__header th');
        return {
            found: true,
            rowCount: rows.length,
            headers: Array.from(headers).map(h => h.textContent.trim()),
            firstRow: Array.from(rows[0]?.querySelectorAll('td') || []).map(d => d.textContent.trim())
        };
    };

    const assertText = (selector, expected) => {
        const el = document.querySelector(selector);
        if (!el) return { found: false, error: 'Element not found: ' + selector };
        const text = el.textContent.trim();
        return { found: true, text, match: text.includes(expected) };
    };

    const getSelectOptions = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return { found: false };
        const options = el.querySelectorAll('option, .el-select-dropdown__item');
        return {
            found: true,
            count: options.length,
            values: Array.from(options).map(o => o.value || o.textContent.trim())
        };
    };

    const waitForStore = (storeName, property, timeout = 10000) => {
        return new Promise((resolve, reject) => {
            const start = Date.now();
            const check = () => {
                const store = getStore(storeName);
                if (store && store[property] !== undefined && store[property] !== null) {
                    resolve({ ready: true, value: serializeValue(store[property]) });
                    return;
                }
                if (Date.now() - start > timeout) {
                    reject(new Error('Timeout waiting for ' + storeName + '.' + property));
                    return;
                }
                setTimeout(check, 100);
            };
            check();
        });
    };

    // ============================================================
    // EXPORT
    // ============================================================

    return {
        // 原有
        snapshot,
        diff,
        startWatching,
        getMutations,
        getComponentState,
        assertTable,
        assertText,
        getSelectOptions,
        waitForStore,
        getStore,
        pinia,

        // 新增：突变可识别性
        startDOMTracking,
        getDOMMutations,
        stopDOMTracking,
        startNetworkTracking,
        getNetworkRequests,
        getPendingRequests,
        stopNetworkTracking,
        startAllTracking,
        getAllChanges,
        waitForStable,

        // 新增：内容可验证性
        verifyTableConsistency,
        verifyFormConsistency,
        detectErrorStates,
        verifyTableData,
        verifyPageStructure,
        getVisibleTextNodes
    };
})();