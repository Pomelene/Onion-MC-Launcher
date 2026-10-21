"""Shared remote URL and redirect policy; response bodies are never errors."""
import urllib.parse
import urllib.request


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
    return urllib.request.build_opener(SafeRedirectHandler()).open(request,timeout=timeout)
