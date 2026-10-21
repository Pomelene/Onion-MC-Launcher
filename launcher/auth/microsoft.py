"""Microsoft device authorization, Xbox and Minecraft authentication.
OAuth endpoints require form bodies; Xbox/Minecraft endpoints require JSON.
"""
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional
from ..network import secure_open

DEVICE_CODE_URL = 'https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode'
TOKEN_URL = 'https://login.microsoftonline.com/consumers/oauth2/v2.0/token'
XBL_URL = 'https://user.auth.xboxlive.com/user/authenticate'
XSTS_URL = 'https://xsts.auth.xboxlive.com/xsts/authorize'
MC_LOGIN_URL = 'https://api.minecraftservices.com/authentication/login_with_xbox'
MC_PROFILE_URL = 'https://api.minecraftservices.com/minecraft/profile'
SCOPE = 'XboxLive.signin offline_access'


class AuthError(Exception):
    """A safe diagnostic: never include raw authentication response bodies."""
    def __init__(self, message, *, code='', status=0):
        super().__init__(message)
        self.code, self.status = code, status


class LoginCancelled(AuthError):
    def __init__(self):
        super().__init__('登录已取消', code='cancelled')


@dataclass
class DeviceCode:
    user_code: str
    verification_uri: str
    device_code: str
    expires_in: int
    interval: int
    message: str


def _error(url, status, data):
    code = str(data.get('error') or data.get('XErr') or '')
    messages = {
        'authorization_pending': '正在等待浏览器授权',
        'slow_down': '服务器要求降低授权查询频率',
        'authorization_declined': '你已拒绝本次授权，可以重新登录',
        'access_denied': '本次授权被拒绝，可以重新登录',
        'expired_token': '设备码已过期，请重新获取',
        'code_expired': '设备码已过期，请重新获取',
        'bad_verification_code': '设备码无效，请重新获取',
        'invalid_client': 'Microsoft 应用配置无效，请检查 client_id 和公共客户端设置',
        'unauthorized_client': '此 Microsoft 应用未允许该登录方式，请检查应用配置',
        'invalid_grant': '登录授权已失效，请重新登录微软账号',
        'invalid_scope': '应用未获准请求 Xbox 登录权限，请检查应用配置',
        '2148916233': '账号尚未创建 Xbox 档案，请先在 xbox.com 完成账号设置',
        '2148916235': '该账号所在地区不支持 Xbox Live',
        '2148916236': '该账号需要先完成 Xbox 成人验证',
        '2148916237': '该账号需要先完成 Xbox 成人验证',
        '2148916238': '该账号需要由监护人完成 Microsoft 家庭组设置',
    }
    if code in messages:
        return AuthError(messages[code], code=code, status=status)
    if url == MC_PROFILE_URL and status == 404:
        message = '未找到 Java 版玩家档案，请确认此账号拥有 Java 版或有效订阅，并已设置玩家名称'
    elif url == MC_LOGIN_URL and status == 403:
        # Only recognize a fixed public error phrase; never echo the raw body.
        description=data.get('errorMessage') or data.get('error_description') or ''
        if isinstance(description,str) and description.lower().startswith('invalid app registration'):
            return AuthError('Minecraft 服务未允许此应用登录，需要由启动器维护者申请应用访问资格',code='invalid_app_registration',status=status)
        return AuthError('微软与 Xbox 授权已完成，但 Minecraft 服务拒绝访问（HTTP 403）；请由维护者核查应用访问资格及服务策略',code='minecraft_forbidden',status=status)
    elif status == 429:
        message = '登录请求过于频繁，请稍后重试'
    elif status >= 500:
        message = '认证服务暂时不可用，请稍后重试'
    elif status == 401:
        message = '登录凭据已失效，请重新登录'
    else:
        message = f'认证请求失败（HTTP {status}），请检查网络及应用配置'
    # Unknown codes/bodies may contain tokens or personal information. Do not echo them.
    return AuthError(message, status=status)


def _request(req):
    try:
        with secure_open(req, timeout=20) as response:
            content=response.read(1024**2+1)
            if len(content)>1024**2:raise AuthError('认证响应超过安全上限',code='invalid_response')
            data = json.loads(content.decode('utf-8'))
        if not isinstance(data, dict):
            raise AuthError('认证服务返回了无效的数据')
        return data
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read(65536).decode('utf-8', 'replace'))
            if not isinstance(data, dict):
                data = {}
        except (ValueError, OSError):
            data = {}
        raise _error(req.full_url, exc.code, data) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AuthError('无法连接认证服务，请检查网络或系统代理后重试', code='network') from None
    except (ValueError, UnicodeError):
        raise AuthError('认证服务返回了无效的数据，请稍后重试') from None


def _post_json(url, payload, headers=None):
    return _request(urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'User-Agent': 'OnionMinecraftLauncher/0.2.0', **(headers or {})}))


def _post_form(url, payload):
    return _request(urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode('ascii'), method='POST', headers={
        'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json',
        'User-Agent': 'OnionMinecraftLauncher/0.2.0'}))


def _get_json(url, token):
    return _request(urllib.request.Request(url, headers={'Authorization': f'Bearer {token}',
        'Accept': 'application/json', 'User-Agent': 'OnionMinecraftLauncher/0.2.0'}))


def _required(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthError('认证服务响应缺少必要信息，请重新登录', code='invalid_response')
    return value


def verification_url(url):
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme != 'https' or parsed.hostname not in
            {'microsoft.com', 'www.microsoft.com', 'login.microsoftonline.com', 'login.live.com'}
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise AuthError('认证服务返回了非微软的授权地址，已停止打开', code='invalid_response')
    return url


def request_device_code(client_id):
    if not client_id or not client_id.strip():
        raise AuthError('请先配置你自己的 Microsoft 应用 client_id', code='invalid_client')
    data = _post_form(DEVICE_CODE_URL, {'client_id': client_id.strip(), 'scope': SCOPE})
    try:
        return DeviceCode(_required(data, 'user_code'), verification_url(_required(data, 'verification_uri')),
                          _required(data, 'device_code'), max(1, int(data.get('expires_in', 900))),
                          max(1, int(data.get('interval', 5))), '')
    except (TypeError, ValueError):
        raise AuthError('认证服务返回了无效的设备码信息') from None


def _check_cancel(should_cancel):
    if should_cancel and should_cancel():
        raise LoginCancelled()


def _wait(seconds, should_cancel):
    deadline = time.monotonic() + seconds
    while True:
        _check_cancel(should_cancel)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(.2, remaining))


def poll_for_token(client_id, device_code, should_cancel=None, on_step=None):
    deadline = time.monotonic() + device_code.expires_in
    interval = max(1, device_code.interval)
    network_failures=0
    while True:
        _check_cancel(should_cancel)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AuthError('设备码已过期，请重新获取', code='expired_token')
        _wait(min(interval, remaining), should_cancel)
        if time.monotonic() >= deadline:
            raise AuthError('设备码已过期，请重新获取', code='expired_token')
        try:
            token = _post_form(TOKEN_URL, {'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                                         'client_id': client_id, 'device_code': device_code.device_code})
            _required(token, 'access_token')
            _check_cancel(should_cancel)
            return token
        except AuthError as exc:
            if exc.code == 'authorization_pending':
                network_failures=0
                continue
            if exc.code == 'slow_down':
                interval += 5
                continue
            if exc.code=='network' or exc.status in (429,500,502,503,504):
                # Keep the SAME device code through temporary failures. Losing
                # this in-memory session discards a browser authorization that
                # may already have completed. Deadline and cancellation remain.
                network_failures+=1
                if on_step:on_step('认证连接暂时中断，正在重试；已完成的网页授权无需重复操作')
                _wait(min(30,2**min(network_failures,5),max(0,deadline-time.monotonic())),should_cancel)
                continue
            raise


def refresh_token(client_id, refresh):
    return _post_form(TOKEN_URL, {'grant_type': 'refresh_token', 'client_id': client_id,
                                 'refresh_token': refresh, 'scope': SCOPE})


def xbox_authenticate(ms_access_token):
    data = _post_json(XBL_URL, {'Properties': {'AuthMethod': 'RPS', 'SiteName': 'user.auth.xboxlive.com',
                      'RpsTicket': f'd={ms_access_token}'}, 'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT'})
    uhs = _user_hash(data)
    return _required(data, 'Token'), uhs


def xsts_authorize(xbl_token):
    data = _post_json(XSTS_URL, {'Properties': {'SandboxId': 'RETAIL', 'UserTokens': [xbl_token]},
                               'RelyingParty': 'rp://api.minecraftservices.com/', 'TokenType': 'JWT'})
    uhs = _user_hash(data)
    return _required(data, 'Token'), uhs


def _user_hash(data):
    try:
        uhs=data['DisplayClaims']['xui'][0]['uhs']
        if not isinstance(uhs,str) or not uhs:raise ValueError()
        return uhs
    except (KeyError,IndexError,TypeError,ValueError):
        raise AuthError('Xbox 授权响应缺少用户信息，请重新登录',code='invalid_response') from None


def _minecraft_token(uhs, xsts_token, client_id=''):
    identity=f'XBL3.0 x={uhs};{xsts_token}'
    data = _post_json(MC_LOGIN_URL, {'identityToken': identity})
    _required(data, 'access_token')
    return data


def login_with_xbox(uhs, xsts_token):
    return _minecraft_token(uhs, xsts_token)['access_token']


def fetch_profile(mc_access_token):
    data = _get_json(MC_PROFILE_URL, mc_access_token)
    import uuid
    try:
        player_id = uuid.UUID(_required(data, 'id')).hex
    except ValueError:
        raise AuthError('Minecraft 服务返回了无效的玩家 UUID') from None
    return player_id, _required(data, 'name')


def token_xuid(token):
    """Optional launch metadata only; decoded claims are never authentication proof."""
    try:
        payload = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        return str(claims.get('xuid') or '')
    except (ValueError, IndexError, UnicodeError, AttributeError, TypeError):
        return ''


def _complete_login(token, previous_refresh='', should_cancel=None, on_step=None, client_id=''):
    def step(text):
        _check_cancel(should_cancel)
        if on_step:
            on_step(text)
    step('正在验证 Xbox Live 账号')
    xbl, xbl_uhs = xbox_authenticate(_required(token, 'access_token'))
    step('正在获取 Xbox 游戏授权')
    xsts, uhs = xsts_authorize(xbl)
    if xbl_uhs!=uhs:raise AuthError('Xbox 登录身份不一致，请重新授权',code='identity_mismatch')
    step('正在登录 Minecraft 服务')
    minecraft = _minecraft_token(uhs, xsts, client_id)
    # Minecraft and Microsoft access tokens have separate lifetimes.
    try:
        expires = max(1, int(minecraft.get('expires_in', 3600)))
    except (TypeError, ValueError):
        raise AuthError('Minecraft 服务返回了无效的有效期') from None
    expires_at = time.time() + expires
    step('正在读取 Java 版玩家档案')
    uid, name = fetch_profile(minecraft['access_token'])
    _check_cancel(should_cancel)
    return {'username': name, 'uuid': uid, 'access_token': minecraft['access_token'],
            'refresh_token': token.get('refresh_token') or previous_refresh,
            'expires_at': expires_at, 'xuid': token_xuid(minecraft['access_token'])}


def refresh_minecraft(client_id, refresh):
    if not client_id or not refresh:
        raise AuthError('账号缺少续期信息，请重新登录', code='invalid_grant')
    return _complete_login(refresh_token(client_id, refresh), refresh,client_id=client_id)


def login_with_device_code(client_id, on_code, should_cancel=None, on_step=None):
    _check_cancel(should_cancel)
    if on_step:
        on_step('正在获取微软授权码')
    code = request_device_code(client_id)
    _check_cancel(should_cancel)
    on_code(code)
    if on_step:
        on_step('等待你在浏览器中授权')
    token = poll_for_token(client_id, code, should_cancel,on_step)
    return _complete_login(token, should_cancel=should_cancel, on_step=on_step,client_id=client_id)
