"""Credential-free authentication transport probes; never starts a login flow.

Direct DNS/TLS and urllib's effective system/environment proxy route are tested
separately. HTTP rejection proves transport only, never successful authorization.
No response bodies, proxy addresses, account files or credentials are recorded.
"""
import concurrent.futures
import datetime
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher.auth import microsoft as auth


def probe(item):
    name, url, payload, form = item
    host = urllib.parse.urlsplit(url).hostname
    result = {'name': name, 'url': url}
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        result['dns'] = 'ok'
    except OSError as error:
        result['dns'] = type(error).__name__
    start = time.monotonic()
    try:
        with socket.create_connection((host, 443), timeout=8) as connection:
            with ssl.create_default_context().wrap_socket(connection, server_hostname=host) as tls:
                result['direct_tls'] = {'result': 'ok', 'version': tls.version(), 'certificate_verified': True}
    except OSError as error:
        result['direct_tls'] = {'result': type(error).__name__}
    result['direct_tls_ms'] = round((time.monotonic() - start) * 1000)
    headers = {'Accept': 'application/json', 'User-Agent': 'CraftBridge/0.2.0'}
    body = None
    if payload is not None:
        body = (urllib.parse.urlencode(payload).encode('ascii') if form
                else json.dumps(payload).encode('utf-8'))
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    request = urllib.request.Request(url, data=body, headers=headers)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result['http_status'] = response.status
            result['content_type'] = response.headers.get_content_type()
    except urllib.error.HTTPError as error:
        result['http_status'] = error.code
        result['content_type'] = error.headers.get_content_type()
        # Only allow known protocol codes; raw responses may contain request IDs.
        try:
            data = json.loads(error.read(16384))
            code = data.get('error') if isinstance(data, dict) else None
            if code in {'invalid_request', 'invalid_client', 'unauthorized_client', 'invalid_grant', 'invalid_scope'}:
                result['oauth_error'] = code
        except (ValueError, OSError):
            pass
        error.close()
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, 'reason', error)
        result['http_error'] = type(reason).__name__
    result['http_ms'] = round((time.monotonic() - start) * 1000)
    result['transport_reached_http'] = 'http_status' in result
    return result


def main():
    # Invalid public application and absent credentials: no usable device code or
    # token can be issued, and no personal account is involved.
    invalid_id = '00000000-0000-0000-0000-000000000000'
    endpoints = [
        ('Microsoft device code', auth.DEVICE_CODE_URL, {'client_id': invalid_id, 'scope': auth.SCOPE}, True),
        ('Microsoft token', auth.TOKEN_URL, {'client_id': invalid_id, 'grant_type': 'refresh_token', 'refresh_token': ''}, True),
        ('Xbox Live', auth.XBL_URL, {}, False),
        ('Xbox XSTS', auth.XSTS_URL, {}, False),
        ('Minecraft login', auth.MC_LOGIN_URL, {}, False),
        ('Minecraft profile', auth.MC_PROFILE_URL, None, False),
        ('Minecraft entitlements (HMCL reference)', 'https://api.minecraftservices.com/entitlements/mcstore', None, False),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        results = list(pool.map(probe, endpoints))
    report = {
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'real_account_authorization': False, 'credentials_used': False,
        'proxy_configured': bool(urllib.request.getproxies().get('https')),
        'certificate_verification_disabled': False,
        'limitation': 'Unauthenticated probes validate transport and rejection only; they do not validate client eligibility, tokens or ownership.',
        'endpoints': results,
    }
    path = ROOT / 'docs/auth-network-check.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
