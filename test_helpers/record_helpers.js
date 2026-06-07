/**
 * Browser-side recording helpers for user action capture.
 *
 * Injected via page.evaluate() by the Python Recorder.
 * Captures: click, dblclick, input, change, keydown, navigation events.
 *
 * Retrieval: window.__recorder__.getEvents() -> returns captured events as JSON.
 */

window.__recorder__ = (() => {
    const events = [];
    let recording = false;
    let lastClickTime = 0;
    let lastClickTarget = null;
    let inputTimers = {};
    let lastUrl = location.href;

    const CLICK_DEDUP_WINDOW = 300;

    const MAX_EVENTS = 5000;

    const getPagePath = () => {
        const u = new URL(location.href);
        return u.pathname + u.search + u.hash;
    };

    const buildSelectors = (el) => {
        if (!el || el.nodeType !== 1) return null;

        const selectors = [];
        const tag = el.tagName.toLowerCase();

        const testId = el.getAttribute('data-testid');
        if (testId) {
            selectors.push(`[data-testid="${testId}"]`);
        }

        const id = el.id;
        if (id && /^[a-zA-Z][\w-]*$/.test(id)) {
            const count = document.querySelectorAll('#' + CSS.escape(id)).length;
            if (count === 1) {
                selectors.push('#' + CSS.escape(id));
            }
        }

        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.length < 60) {
            selectors.push(`[aria-label="${ariaLabel}"]`);
        }

        const text = (el.textContent || '').trim().slice(0, 80);
        const placeholder = el.getAttribute('placeholder') || '';

        if (tag === 'input' || tag === 'textarea') {
            if (placeholder) {
                selectors.push(`${tag}[placeholder="${placeholder}"]`);
            }
            const name = el.getAttribute('name');
            if (name) {
                selectors.push(`${tag}[name="${name}"]`);
            }
            const type = el.getAttribute('type');
            if (type) {
                const sel = `${tag}[type="${type}"]`;
                if (document.querySelectorAll(sel).length === 1) {
                    selectors.push(sel);
                }
            }
        }

        if (tag === 'button' || tag === 'a' || (tag === 'span' && el.closest('button'))) {
            const actual = tag === 'span' ? el.closest('button') : el;
            if (actual && text && text.length < 40) {
                selectors.push(`${actual.tagName.toLowerCase()}:has-text("${text}")`);
            }
        }

        const cls = el.className && typeof el.className === 'string'
            ? el.className.split(/\s+/).filter(c => c && !c.match(/^(is-|el-|--)/)).slice(0, 3)
            : [];
        if (cls.length > 0) {
            const clsSel = tag + '.' + cls.join('.');
            const count = document.querySelectorAll(clsSel).length;
            if (count === 1) {
                selectors.push(clsSel);
            } else if (count <= 3 && text) {
                selectors.push(`${clsSel}:has-text("${text}")`);
            }
        }

        const elPlusClasses = (el.className && typeof el.className === 'string'
            ? el.className.split(/\s+/) : [])
            .filter(c => c.startsWith('el-'));
        if (elPlusClasses.length > 0 && text) {
            const epSel = tag + '.' + elPlusClasses.join('.');
            selectors.push(`${epSel}:has-text("${text}")`);
        }

        const xpath = buildXPath(el);
        if (xpath) {
            selectors.push('xpath=' + xpath);
        }

        return selectors.length > 0 ? selectors : null;
    };

    const buildXPath = (el) => {
        if (!el || el.nodeType !== 1) return null;
        if (el.id) return `//*[@id="${el.id}"]`;

        const parts = [];
        let current = el;
        while (current && current.nodeType === 1 && current !== document.body) {
            let segment = current.tagName.toLowerCase();
            const id = current.id;
            if (id) {
                parts.unshift(`*[@id="${id}"]`);
                break;
            }
            const parent = current.parentElement;
            if (parent) {
                const siblings = Array.from(parent.children).filter(
                    c => c.tagName === current.tagName
                );
                if (siblings.length > 1) {
                    const idx = siblings.indexOf(current) + 1;
                    segment += `[${idx}]`;
                }
            }
            parts.unshift(segment);
            current = current.parentElement;
        }
        return '//' + parts.join('/');
    };

    const recordEvent = (type, target, value) => {
        if (!recording) return;
        if (events.length >= MAX_EVENTS) return;

        const now = Date.now();
        if (type === 'click' || type === 'dblclick') {
            if (type === 'click' && now - lastClickTime < CLICK_DEDUP_WINDOW && target === lastClickTarget) {
                return;
            }
            lastClickTime = now;
            lastClickTarget = target;
        }

        const selectors = buildSelectors(target);
        if (!selectors) return;

        const record = {
            seq: events.length + 1,
            type: type,
            timestamp: now,
            target: {
                selector: selectors[0],
                fallback_selectors: selectors.slice(1, 5),
                text: (target.textContent || '').trim().slice(0, 100),
                tag: target.tagName.toLowerCase(),
                classes: target.className && typeof target.className === 'string'
                    ? target.className.split(/\s+/).slice(0, 10)
                    : []
            },
            page_url: getPagePath(),
            value: value !== undefined ? value : null
        };

        events.push(record);
    };

    const onDocumentClick = (e) => {
        let target = e.target;
        if (target && target.nodeType !== 1) {
            target = target.parentElement;
        }
        if (!target) return;

        if (target.closest && target.closest('.el-select-dropdown__item')) {
            target = target.closest('.el-select-dropdown__item');
            recordEvent('click', target, target.textContent.trim());
            return;
        }

        if (target.closest && target.closest('.el-dropdown-menu__item')) {
            target = target.closest('.el-dropdown-menu__item');
            recordEvent('click', target, target.textContent.trim());
            return;
        }

        if (target.closest && target.closest('.el-tree-node__content')) {
            target = target.closest('.el-tree-node__content');
            const label = target.querySelector('.el-tree-node__label');
            recordEvent('click', target, label ? label.textContent.trim() : null);
            return;
        }

        if (target.closest && target.closest('.el-pagination button')) {
            target = target.closest('.el-pagination button');
            recordEvent('click', target, target.textContent.trim());
            return;
        }

        recordEvent('click', target);
    };

    const onDocumentDblClick = (e) => {
        const target = e.target && e.target.nodeType === 1 ? e.target : e.target.parentElement;
        if (target) {
            recordEvent('dblclick', target);
        }
    };

    const onDocumentInput = (e) => {
        const target = e.target;
        if (!target || !target.matches) return;
        if (!target.matches('input, textarea, [contenteditable="true"]')) return;

        const key = target.id || target.name || target.className;
        if (inputTimers[key]) {
            clearTimeout(inputTimers[key]);
        }
        inputTimers[key] = setTimeout(() => {
            recordEvent('input', target, target.value !== undefined ? target.value : target.textContent);
            delete inputTimers[key];
        }, 400);
    };

    const onDocumentChange = (e) => {
        const target = e.target;
        if (!target || !target.matches) return;

        if (target.matches('select')) {
            recordEvent('select', target, target.value);
        } else if (target.matches('input[type="checkbox"]')) {
            recordEvent('check', target, target.checked);
        } else if (target.matches('.el-switch input[type="checkbox"]')) {
            const sw = target.closest('.el-switch');
            recordEvent('toggle', sw || target, target.checked);
        }
    };

    const onDocumentKeyDown = (e) => {
        if (e.key === 'Enter') {
            const target = e.target;
            if (target && target.matches && target.matches('input, textarea, select')) {
                recordEvent('keydown', target, 'Enter');
            }
        } else if (e.key === 'Escape') {
            recordEvent('keydown', document.activeElement || document.body, 'Escape');
        } else if (e.key === 'Tab' && e.target && e.target.matches) {
            recordEvent('keydown', e.target, 'Tab');
        }
    };

    const onPopState = () => {
        const newUrl = getPagePath();
        if (newUrl !== lastUrl) {
            lastUrl = newUrl;
            events.push({
                seq: events.length + 1,
                type: 'navigate',
                timestamp: Date.now(),
                target: { selector: '', fallback_selectors: [], text: '', tag: '', classes: [] },
                page_url: newUrl,
                value: newUrl
            });
        }
    };

    const urlPollInterval = null;

    const start = () => {
        if (recording) return 'already recording';
        events.length = 0;
        recording = true;
        lastUrl = getPagePath();

        document.addEventListener('click', onDocumentClick, true);
        document.addEventListener('dblclick', onDocumentDblClick, true);
        document.addEventListener('input', onDocumentInput, true);
        document.addEventListener('change', onDocumentChange, true);
        document.addEventListener('keydown', onDocumentKeyDown, true);
        window.addEventListener('popstate', onPopState);
        window.addEventListener('hashchange', onPopState);

        events.push({
            seq: 0,
            type: 'navigate',
            timestamp: Date.now(),
            target: { selector: '', fallback_selectors: [], text: '', tag: '', classes: [] },
            page_url: getPagePath(),
            value: getPagePath()
        });

        return 'recording started at ' + getPagePath();
    };

    const stop = () => {
        recording = false;
        document.removeEventListener('click', onDocumentClick, true);
        document.removeEventListener('dblclick', onDocumentDblClick, true);
        document.removeEventListener('input', onDocumentInput, true);
        document.removeEventListener('change', onDocumentChange, true);
        document.removeEventListener('keydown', onDocumentKeyDown, true);
        window.removeEventListener('popstate', onPopState);
        window.removeEventListener('hashchange', onPopState);

        for (const key in inputTimers) {
            clearTimeout(inputTimers[key]);
        }
        inputTimers = {};

        const result = [...events];
        events.length = 0;
        return result;
    };

    const getEvents = () => {
        const result = [...events];
        events.length = 0;
        return result;
    };

    const isRecording = () => recording;

    const getEventCount = () => events.length;

    return {
        start,
        stop,
        getEvents,
        isRecording,
        getEventCount
    };
})();
