"""Shared remote URL and redirect policy; response bodies are never errors."""
import http.client
import time
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request

_TLS_CONTEXT=None
_TLS_CREATED=0.0
_TLS_LOCK=threading.Lock()


def https_handler():
    """Reuse immutable TLS trust configuration, not connections or credentials."""
    global _TLS_CONTEXT,_TLS_CREATED
    with _TLS_LOCK:
        now=time.monotonic()
        if (_TLS_CONTEXT is None or now-_TLS_CREATED>=300 or not _TLS_CONTEXT.check_hostname
                or _TLS_CONTEXT.verify_mode!=ssl.CERT_REQUIRED):
            context=ssl.create_default_context()
            context.set_alpn_protocols(['http/1.1'])
            if hasattr(context,'post_handshake_auth'):context.post_handshake_auth=True
            _TLS_CONTEXT=context;_TLS_CREATED=now
        context=_TLS_CONTEXT
    return urllib.request.HTTPSHandler(context=context)


def validate_url(url, *, https_only=False):
    if not isinstance(url,str) or any(ord(c)<32 for c in url) or '\\' in url:
        raise ValueError('下载地址格式无效')
    try:
        parsed=urllib.parse.urlsplit(url)
        schemes=('https',) if https_only else ('https','http')
        if (parsed.scheme not in schemes or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port==0):raise ValueError()
        parsed.port
    except ValueError:
        raise ValueError('只允许无内嵌凭据的远程 HTTP(S) 地址') from None
    return url


def _origin(url):
    p=urllib.parse.urlsplit(url)
    return p.scheme,p.hostname,p.port or (443 if p.scheme=='https' else 80)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_url(newurl)
        if urllib.parse.urlsplit(req.full_url).scheme=='https' and urllib.parse.urlsplit(newurl).scheme!='https':
            raise ValueError('拒绝将 HTTPS 请求降级为明文连接')
        target=super().redirect_request(req,fp,code,msg,headers,newurl)
        if target and _origin(req.full_url)!=_origin(newurl):
            for key in list(target.headers):
                if key.lower() in ('authorization','proxy-authorization','x-api-key','cookie'):
                    target.remove_header(key)
        return target


def secure_open(request,timeout=20):
    validate_url(request.full_url,https_only=True)
    return urllib.request.build_opener(SafeRedirectHandler(),https_handler()).open(request,timeout=timeout)


def fetch_public(request, *, limit, timeout=20, proxy=None):
    """Read an anonymous HTTPS GET; retry a broken proxy once over direct TLS.

    Kept separate from secure_open: logins, uploads and credential-bearing
    requests must never acquire automatic route changes or replay semantics.
    """
    validate_url(request.full_url,https_only=True)
    headers=dict(request.header_items())
    if request.get_method()!='GET' or request.data is not None or any(
            key.lower() in ('authorization','proxy-authorization','cookie','x-api-key') for key in headers):
        raise ValueError('公开请求只能是不含凭据的 GET')
    proxies={'http':proxy,'https':proxy} if proxy else urllib.request.getproxies()
    routes=[proxies,{}] if proxies.get('https') else [{}]
    deadline=time.monotonic()+timeout
    for index,route in enumerate(routes):
        remaining=max(.1,deadline-time.monotonic())
        attempt_timeout=min(remaining,timeout/2) if index==0 and len(routes)>1 else remaining
        # ProxyHandler mutates Requests (including proxy credentials). Each
        # attempt starts from the original anonymous URL and headers.
        fresh=urllib.request.Request(request.full_url,headers=headers,method='GET')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler(route),SafeRedirectHandler(),https_handler())
        try:
            with opener.open(fresh,timeout=attempt_timeout) as response:
                body=response.read(limit+1)
            if len(body)>limit:raise ValueError('响应内容超过安全上限')
            return body
        except urllib.error.HTTPError as error:
            # Shared proxy exit IPs can exhaust GitHub's anonymous API quota.
            rate_limited=error.code==429 or (error.code==403 and error.headers and error.headers.get('X-RateLimit-Remaining')=='0')
            if index==len(routes)-1 or (error.code not in (407,502,503,504) and not rate_limited):raise
            error.close()
        except (urllib.error.URLError,OSError,http.client.HTTPException):
            if index==len(routes)-1:raise
