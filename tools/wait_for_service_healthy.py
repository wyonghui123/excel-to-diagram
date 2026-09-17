#!/usr/bin/env python3
"""wait_for_service_healthy.py - HTTP-level health check + retry for staging services.

[P1-8 2026-09-01] Goes beyond TCP port check (wait_for_service_up in staging_ops).
Waits until the HTTP endpoint returns 2xx, with exponential backoff.

Distinguishes:
  - TCP up + HTTP 2xx  -> healthy
  - TCP up + HTTP 5xx  -> service starting (likely crash; warn and continue)
  - TCP up + HTTP 4xx  -> service up but auth required (not healthy for our purpose)
  - TCP down           -> service not started yet (wait)

Usage:
    from wait_for_service_healthy import wait_for_healthy
    wait_for_healthy(host='172.20.59.7', port=19200, path='/api/health',
                     timeout=30, initial_interval=0.5, max_interval=5.0)

CLI:
    python wait_for_service_healthy.py --port 19200 --path /api/health --timeout 30
"""
import sys
import time
import http.client
import argparse


def wait_for_healthy(host, port, path='/api/health', method='GET',
                     expected_status_min=200, expected_status_max=299,
                     timeout=30, initial_interval=0.5, max_interval=5.0,
                     accept_404=False, label=None):
    """Poll HTTP endpoint until 2xx (or timeout).

    Args:
        host: hostname/IP
        port: TCP port
        path: URL path to probe (e.g. '/api/health', '/api/v2/health')
        method: HTTP method (default GET)
        expected_status_min/max: inclusive range for "healthy"
        timeout: max total wait in seconds
        initial_interval: first poll interval (s)
        max_interval: cap on backoff (s)
        accept_404: if True, HTTP 404 is treated as healthy (port up, service
                    running, endpoint just doesn't exist on this service)
        label: optional service name for logging

    Returns:
        dict with final probe result: {'status', 'elapsed_ms', 'attempts'}

    Raises:
        TimeoutError: if no healthy response within timeout
    """
    label = label or f'{host}:{port}{path}'
    deadline = time.time() + timeout
    interval = initial_interval
    attempt = 0
    last_status = None
    last_err = None
    start = time.time()

    while time.time() < deadline:
        attempt += 1
        try:
            conn = http.client.HTTPConnection(host, port, timeout=3)
            conn.request(method, path)
            resp = conn.getresponse()
            status = resp.status
            conn.close()
            last_status = status
            in_range = expected_status_min <= status <= expected_status_max
            if in_range or (accept_404 and status == 404):
                return {
                    'status': status,
                    'elapsed_ms': int((time.time() - start) * 1000),
                    'attempts': attempt,
                    'label': label,
                    'healthy': True,
                }
        except (ConnectionRefusedError, OSError) as e:
            last_err = str(e)
        except Exception as e:
            last_err = f'{type(e).__name__}: {e}'

        # Exponential backoff (capped to remaining time, never negative)
        remaining = max(0.0, deadline - time.time())
        time.sleep(min(interval, remaining))
        interval = min(interval * 2, max_interval)

    raise TimeoutError(
        f'{label} not healthy after {timeout}s '
        f'(attempts={attempt}, last_status={last_status}, last_err={last_err})'
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--path', default='/api/health')
    p.add_argument('--method', default='GET')
    p.add_argument('--timeout', type=int, default=30)
    p.add_argument('--initial-interval', type=float, default=0.5)
    p.add_argument('--max-interval', type=float, default=5.0)
    p.add_argument('--accept-404', action='store_true')
    p.add_argument('--label', default=None)
    args = p.parse_args()

    try:
        result = wait_for_healthy(
            host=args.host,
            port=args.port,
            path=args.path,
            method=args.method,
            timeout=args.timeout,
            initial_interval=args.initial_interval,
            max_interval=args.max_interval,
            accept_404=args.accept_404,
            label=args.label,
        )
        print(f'HEALTHY: {result}')
        sys.exit(0)
    except TimeoutError as e:
        print(f'TIMEOUT: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
