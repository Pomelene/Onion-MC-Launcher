"""Distributor application identity, independent of account secrets."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from launcher.auth.application import resolve_client_id,valid_client_id

APP='00000000-0000-4000-8000-000000000001'
OTHER='00000000-0000-4000-8000-000000000002'


def test_application_id_validation():
    assert valid_client_id(APP)
    for value in ('',None,17,'bad','00000000-0000-0000-0000-000000000000'):
        assert not valid_client_id(value)


def test_packaged_application_fallback_and_override():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);(root/'assets').mkdir();path=root/'assets/microsoft-app.json'
        path.write_text(json.dumps({'client_id':APP}),encoding='utf-8')
        with patch('sys._MEIPASS',str(root),create=True):
            assert resolve_client_id({})==APP
            assert resolve_client_id({'microsoft_client_id':OTHER})==OTHER
            assert resolve_client_id({'microsoft_client_id':OTHER},APP)==APP
            assert resolve_client_id({'microsoft_client_id':'invalid'})==APP
            path.write_text('invalid JSON',encoding='utf-8')
            assert resolve_client_id({})==''
            path.unlink();assert resolve_client_id({})==''
