"""Local PNG skin library and explicit authenticated Minecraft skin upload."""
import hashlib
import json
import struct
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from .network import secure_open
from .safety import contained, component, write_text

MAX_SKIN_BYTES = 1024 * 1024
SKIN_URL = 'https://api.minecraftservices.com/minecraft/profile/skins'
PROFILE_URL = 'https://api.minecraftservices.com/minecraft/profile'
CAPE_URL = PROFILE_URL + '/capes/active'


def _profile_request(account, url, method='GET', body=None):
    if not account or account.type!='microsoft' or not account.access_token or account.is_expired():
        raise ValueError('披风同步需要有效的微软正版登录')
    headers={'Authorization':'Bearer '+account.access_token,'Accept':'application/json','User-Agent':'OnionMinecraftLauncher'}
    if body is not None:headers['Content-Type']='application/json'
    request=urllib.request.Request(url,data=body,method=method,headers=headers)
    try:
        with secure_open(request,timeout=30) as response:
            data=response.read(1048577)
        if len(data)>1048576:raise ValueError('账户资料过大')
        return json.loads(data) if data else {}
    except urllib.error.HTTPError as error:
        status=error.code;error.close();raise RuntimeError(f'披风服务请求失败（HTTP {status}）') from None
    except (urllib.error.URLError,OSError):raise RuntimeError('无法连接披风服务，请稍后重试') from None


def cape_profile(account):
    profile=_profile_request(account,PROFILE_URL)
    if not isinstance(profile,dict) or not isinstance(profile.get('capes',[]),list):raise ValueError('账户披风资料无效')
    return profile


def set_cape(account,cape_id):
    if cape_id is not None:
        cape_id=str(uuid.UUID(cape_id))
        return _profile_request(account,CAPE_URL,'PUT',json.dumps({'capeId':cape_id}).encode())
    return _profile_request(account,CAPE_URL,'DELETE')


def sync_cape(account,cape_id):
    result=set_cape(account,cape_id)
    if not isinstance(result,dict) or not isinstance(result.get('capes'),list):result=cape_profile(account)
    active=[str(item.get('id','')).replace('-','').lower() for item in result.get('capes',[]) if isinstance(item,dict) and item.get('state')=='ACTIVE']
    expected=str(cape_id).replace('-','').lower() if cape_id else None
    if (expected and active!=[expected]) or (not expected and active):
        raise RuntimeError('披风操作已提交，但服务器返回的状态与选择不一致，请刷新后重试')
    return result


def texture_bytes(url):
    from urllib.parse import urlsplit
    from .network import fetch_public
    if not isinstance(url,str):raise ValueError('纹理地址无效')
    parts=urlsplit(url)
    if parts.scheme!='https' or parts.hostname!='textures.minecraft.net' or parts.port not in (None,443) or parts.username or parts.password:
        raise ValueError('纹理地址无效')
    data=fetch_public(urllib.request.Request(url,headers={'User-Agent':'OnionMinecraftLauncher'}),limit=MAX_SKIN_BYTES)
    if len(data)<24 or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':raise ValueError('纹理格式无效')
    width,height=struct.unpack('>II',data[16:24])
    if width>1024 or height>1024 or width<64 or height<32:raise ValueError('纹理尺寸无效')
    return data


def skin_bytes(path):
    with Path(path).open('rb') as source:data = source.read(MAX_SKIN_BYTES+1)
    if len(data)>MAX_SKIN_BYTES:raise ValueError('皮肤文件超过 1 MiB')
    if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('请选择有效的 PNG 皮肤文件（最大 1 MiB）')
    width, height = struct.unpack('>II', data[16:24])
    if (width, height) not in ((64, 64), (64, 32)):
        raise ValueError('皮肤尺寸必须为 64 × 64 或 64 × 32')
    return data


class SkinLibrary:
    def __init__(self, app_root):
        self.root = Path(app_root) / '.onion' / 'skins'
        self.selections = self.root / 'selections.json'

    def favorites(self):
        path=contained(self.root/'favorites.json',self.root)
        try:
            if path.stat().st_size>65536:raise ValueError('皮肤收藏文件过大')
            data=json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:return set()
        if not isinstance(data,list):raise ValueError('皮肤收藏格式无效')
        return {value for value in data if isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)}

    def is_favorite(self,path):return hashlib.sha256(skin_bytes(contained(Path(path),self.root))).hexdigest() in self.favorites()

    def set_favorite(self,path,favorite):
        digest=hashlib.sha256(skin_bytes(contained(Path(path),self.root))).hexdigest()
        self.prepare();values=self.favorites()
        if favorite:values.add(digest)
        else:values.discard(digest)
        write_text(contained(self.root/'favorites.json',self.root),json.dumps(sorted(values)))

    def prepare(self):
        # Refuse linked roots before writing any files.
        contained(self.root, self.root.parent.parent)
        self.root.mkdir(parents=True, exist_ok=True)
        from .log import _hide_directory
        try: _hide_directory(self.root.parent)
        except OSError: pass

    def files(self):
        if not self.root.exists(): return []
        contained(self.root, self.root.parent.parent)
        return sorted((p for p in self.root.iterdir() if p.suffix.lower() == '.png' and p.is_file() and not p.is_symlink()), key=lambda p:p.name.casefold())

    def import_skin(self, source):
        data = skin_bytes(source)
        self.prepare()
        name = component(Path(source).stem)[:80] + '-' + hashlib.sha256(data).hexdigest()[:10] + '.png'
        target = contained(self.root / name, self.root)
        if not target.exists():
            with target.open('xb') as output: output.write(data)
        return target

    def selected(self, account_uuid):
        try:
            item = json.loads(self.selections.read_text(encoding='utf-8')).get(account_uuid, {})
            path = contained(self.root / item['file'], self.root)
            skin_bytes(path)
            return path, item.get('variant', 'classic')
        except (OSError, ValueError, KeyError, TypeError): return None

    def select(self, account_uuid, path, variant):
        if variant not in ('classic', 'slim'): raise ValueError('无效的皮肤模型')
        uuid.UUID(account_uuid)
        path = contained(Path(path), self.root)
        skin_bytes(path);self.prepare()
        try: data = json.loads(self.selections.read_text(encoding='utf-8'))
        except FileNotFoundError: data = {}
        if not isinstance(data, dict): raise ValueError('皮肤配置格式无效')
        data[account_uuid] = {'file': path.name, 'variant': variant}
        write_text(self.selections, json.dumps(data, ensure_ascii=False, indent=2))

    def reset(self,account_uuid):
        self.prepare()
        try:data=json.loads(self.selections.read_text(encoding='utf-8'))
        except FileNotFoundError:return
        data.pop(account_uuid,None)
        write_text(self.selections,json.dumps(data,ensure_ascii=False,indent=2))


def upload_skin(account, path, variant):
    if account.type != 'microsoft' or not account.access_token or account.is_expired():
        raise ValueError('上传皮肤需要有效的微软正版登录')
    if variant not in ('classic', 'slim'): raise ValueError('无效的皮肤模型')
    data = skin_bytes(path)
    boundary = 'OnionSkin' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="variant"\r\n\r\n{variant}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="skin.png"\r\n'
            'Content-Type: image/png\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(SKIN_URL, data=body, method='POST', headers={
        'Authorization': 'Bearer ' + account.access_token,
        'Content-Type': 'multipart/form-data; boundary=' + boundary,
        'User-Agent': 'OnionMinecraftLauncher', 'Accept': 'application/json'})
    try:
        with secure_open(request, timeout=30) as response:
            if response.status not in (200, 201, 204): raise RuntimeError('皮肤上传未成功')
    except urllib.error.HTTPError as error:
        status = error.code;error.close()
        raise RuntimeError(f'皮肤上传失败（HTTP {status}），请检查登录状态后重试') from None
    except (urllib.error.URLError, OSError):
        raise RuntimeError('无法连接皮肤服务，请稍后重试') from None
