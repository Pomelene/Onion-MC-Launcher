import json
import tempfile
import zipfile
from pathlib import Path
from launcher.qtui.content_icons import MAX_ICON_BYTES,read_content_icon


def test_content_icon_metadata_and_pack_fallback():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'example.jar.disabled'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('fabric.mod.json',json.dumps({'icon':{'64':'assets/logo.png'}}))
            archive.writestr('assets/logo.png',b'embedded-artwork')
        assert read_content_icon(path)==b'embedded-artwork'
        pack=Path(folder)/'pack.zip'
        with zipfile.ZipFile(pack,'w') as archive:archive.writestr('pack.png',b'pack-artwork')
        assert read_content_icon(pack)==b'pack-artwork'


def test_content_icon_size_limit_and_broken_archive():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'oversized.zip'
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('pack.png',b'x'*(MAX_ICON_BYTES+1))
        assert read_content_icon(path)==b''
        path.write_bytes(b'not an archive');assert read_content_icon(path)==b''
