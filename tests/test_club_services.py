"""Public service JSON is validated data, never code or launcher credentials."""
import json
import tempfile
from pathlib import Path
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
from launcher.club_services import parse_catalog,fetch_catalog,web_url,read_catalog,sync_catalog,CATALOG_URL,MAX_BYTES

def catalog():
    return {'schema_version':1,'title':'社团服务','categories':[
        {'id':'wiki','title':'社团 Wiki','description':'文档与知识库','tools':[
            {'id':'wiki','title':'社团 Wiki','description':'阅读社团文档','url':'https://wiki.thunion.club/'}]},
        {'id':'map','title':'在线地图','description':'服务器地图','tools':[
            {'id':'map','title':'在线地图','description':'平移缩放服务器地图','url':'https://map.thunion.club/'},
            {'id':'atlas','title':'THUnion Atlas','description':'在线地图，提供离线导航模组下载','url':'https://atlas.thunion.net/'}]}]}

def test_service_catalog_requires_descriptions_and_safe_web_urls():
    assert len(parse_catalog(catalog())['categories'])==2
    assert web_url('http://wiki.thunion.club/')=='http://wiki.thunion.club/'
    assert web_url('http://www.lvss.xyz:14014')=='http://www.lvss.xyz:14014'
    for url in ('javascript:alert(1)','file:///C:/secret','https://user:pass@example.com',
                'https://127.0.0.1','https://[::1]/','https://localhost/','https://server.local/','https://10.1.2.3'):
        try:web_url(url)
        except ValueError:pass
        else:raise AssertionError('Unsafe URL accepted: '+url)
    for change in ('version','description','duplicate','count'):
        data=deepcopy(catalog())
        if change=='version':data['schema_version']=99
        if change=='description':del data['categories'][0]['tools'][0]['description']
        if change=='duplicate':data['categories'][1]['id']='wiki'
        if change=='count':data['categories']*=20
        try:parse_catalog(data)
        except ValueError:pass
        else:raise AssertionError('Invalid catalog accepted')

def test_each_catalog_fetch_requests_fresh_public_document_without_tokens():
    requests=[]
    def open_request(request,timeout):
        requests.append(request);return BytesIO(json.dumps(catalog()).encode())
    with patch('launcher.club_services.secure_open',side_effect=open_request):
        assert fetch_catalog()['categories'][0]['title']=='社团 Wiki';fetch_catalog()
    assert len(requests)==2 and requests[0].full_url!=requests[1].full_url
    for request in requests:
        assert request.full_url.startswith(CATALOG_URL+'?ref=main&fresh=')
        assert not any(key.lower() in ('authorization','cookie') for key in request.headers)

def test_bad_service_payload_is_bounded_and_has_no_command_execution():
    for raw in (b'{' , b'x'*(MAX_BYTES+1),json.dumps({'schema_version':99}).encode()):
        with patch('launcher.club_services.secure_open',return_value=BytesIO(raw)):
            try:fetch_catalog()
            except ValueError:pass
            else:raise AssertionError('Invalid payload accepted')
    payload=catalog();payload['command']='do not run';payload['categories'][0]['tools'][0]['script']='do not run'
    parsed=parse_catalog(payload)
    assert 'command' not in parsed and 'script' not in parsed['categories'][0]['tools'][0]


def test_catalog_cache_preserves_previous_file_when_sync_fails():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'services/webapp.json'
        with patch('launcher.club_services.fetch_catalog',return_value=catalog()):
            assert sync_catalog(path)==catalog()
        original=path.read_bytes()
        with patch('launcher.club_services.fetch_catalog',side_effect=RuntimeError('offline')):
            try:sync_catalog(path)
            except RuntimeError:pass
            else:raise AssertionError('Failed synchronization accepted')
        assert path.read_bytes()==original and read_catalog(path)==catalog()
        with patch('launcher.club_services.fetch_catalog',return_value=catalog()),patch('launcher.club_services.os.replace',side_effect=OSError('locked')):
            try:sync_catalog(path)
            except OSError:pass
            else:raise AssertionError('Failed cache write accepted')
        assert path.read_bytes()==original and list(path.parent.glob('*.tmp'))==[]
        path.write_bytes(b'x'*(MAX_BYTES+1))
        try:read_catalog(path)
        except ValueError:pass
        else:raise AssertionError('Oversized cache accepted')


def test_v2_catalog_order_layout_actions_and_download_integrity():
    import hashlib
    from launcher.club_services import verify_download
    data=catalog();data['schema_version']=2;data['default_category']='map'
    data['categories'].reverse();category=data['categories'][0]
    category.update(layout='list',icon='world',show_urls=False,visible=True)
    tool=category['tools'][0];body=b'fixture'
    tool.update(action='download',filename='263THUnionBasic.mrpack',size=len(body),sha256=hashlib.sha256(body).hexdigest(),button_text='获取基础包',badge='26.3')
    result=parse_catalog(data)
    assert result['categories'][0]['id']=='map' and result['categories'][0]['layout']=='list'
    assert result['default_category']=='map' and result['categories'][0]['tools'][0]['button_text']=='获取基础包'
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/tool['filename'];path.write_bytes(body);verify_download(path,tool)
        path.write_bytes(b'changed')
        try:verify_download(path,tool)
        except ValueError:pass
        else:raise AssertionError('Tampered member download accepted')
    for field,value in (('filename','../unsafe.mrpack'),('filename','test.exe'),('size',True),('sha256','bad'),('url','http://example.com/file'),('action','execute')):
        bad=deepcopy(data);bad['categories'][0]['tools'][0][field]=value
        try:parse_catalog(bad)
        except ValueError:pass
        else:raise AssertionError('Unsafe download field accepted: '+field)
    assert parse_catalog({'schema_version':2,'title':'空目录','categories':[]})['categories']==[]
