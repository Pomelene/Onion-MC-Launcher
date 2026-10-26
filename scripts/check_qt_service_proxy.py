"""Isolated service-session proxy forwarding and offline-cache regression."""
import json,os,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QCoreApplication,QObject
from launcher.qtui.tasks import TaskManager
from launcher.qtui.club_services import ServiceSession
from tests.test_club_services import catalog

app=QCoreApplication([])
def wait(owner):
    deadline=time.monotonic()+5
    while owner.tasks.jobs and time.monotonic()<deadline:
        app.processEvents();time.sleep(.005)
    assert not owner.tasks.jobs

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='service-proxy-') as directory:
    owner=QObject();owner.root=Path(directory)
    owner.repo=SimpleNamespace(downloader=SimpleNamespace(proxy='http://127.0.0.1:7890'))
    owner.tasks=TaskManager(owner)
    session=ServiceSession(owner);events=[];session.changed.connect(lambda:events.append('updated'))
    with patch('launcher.club_services.fetch_public',return_value=json.dumps(catalog()).encode()) as opened:
        session.start();wait(owner);session.start()
        assert opened.call_count==1 and opened.call_args.kwargs['proxy']=='http://127.0.0.1:7890'
        assert session.catalog==catalog() and not session.error and not session.loading and events==['updated']
    original=session.path.read_bytes()
    offline=ServiceSession(owner)
    with patch('launcher.club_services.fetch_public',side_effect=TimeoutError()):
        offline.start();wait(owner)
    assert offline.catalog==catalog() and '连接超时' in offline.error and offline.path.read_bytes()==original
    preview=ServiceSession(owner);preview.preview_path.write_text(json.dumps(catalog()),encoding='utf-8')
    with patch('launcher.club_services.fetch_public') as opened:
        preview.start();wait(owner);opened.assert_not_called()
    assert preview.catalog==catalog() and preview.path.read_bytes()==original
    owner.tasks.pool.waitForDone()
print('PASS: session proxy forwarding, sync once, offline cache, network error and local preview')
