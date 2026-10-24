"""Extract only the official native WebView2 Qt binding, keeping builds small."""
import hashlib,json,sys,urllib.request
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
VERSION='6.12.0'
NAME='pyside6_addons-6.12.0-cp310-abi3-win_amd64.whl'
SHA256='98d8d62010da6605344cee83e5c96fb846170a1f2d924523f10f5d92078b02b0'
FILES=('PySide6/Qt6WebView.dll','PySide6/QtWebView.pyd','PySide6/QtWebView.pyi',
       'PySide6/plugins/webview/qtwebview_webview2.dll')

def main():
    if sys.platform!='win32':raise SystemExit('THUnion native WebView build currently targets Windows x64')
    target=ROOT/'.deps/downloads'/NAME;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(f'https://pypi.org/pypi/PySide6-Addons/{VERSION}/json',timeout=30) as response:metadata=json.load(response)
        url=next(item['url'] for item in metadata['urls'] if item['filename']==NAME)
        if not url.startswith('https://files.pythonhosted.org/'):raise RuntimeError('Unexpected package origin')
        with urllib.request.urlopen(url,timeout=60) as response:payload=response.read(60*1024*1024+1)
        if hashlib.sha256(payload).hexdigest()!=SHA256:raise RuntimeError('Qt WebView package checksum mismatch')
        target.write_bytes(payload)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=SHA256:raise RuntimeError('Qt WebView package checksum mismatch')
    with ZipFile(target) as wheel:
        for name in FILES:
            output=ROOT/'.deps/qt'/name;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(wheel.read(name))
    print('Installed Qt WebView2 binding (no bundled Chromium runtime)')

if __name__=='__main__':main()
