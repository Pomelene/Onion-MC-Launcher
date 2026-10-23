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
