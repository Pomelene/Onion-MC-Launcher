"""Public application identity supplied once by the launcher distributor."""
import json
import sys
import uuid
from pathlib import Path

def valid_client_id(value):
    try:
        return isinstance(value,str) and uuid.UUID(value.strip()).int != 0
    except (ValueError,AttributeError):
        return False


def resolve_client_id(config, explicit=''):
    for value in (explicit,config.get('microsoft_client_id')):
        if valid_client_id(value):return value.strip()
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
    try:
        data=json.loads((root/'assets/microsoft-app.json').read_text(encoding='utf-8'))
        value=data.get('client_id','') if isinstance(data,dict) else ''
        return value.strip() if valid_client_id(value) else ''
    except (OSError,ValueError):
        return ''
