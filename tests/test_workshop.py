"""File boundaries, offline identity and actual cubiomes generation regressions."""
import base64
import hashlib
import json
import struct
import tempfile
import urllib.request
import zlib
from pathlib import Path
from unittest.mock import patch
from launcher.file_library import scan_library,import_files,rename_entry,remove_entry,checked_folder
from launcher.safety import restore_recycled
from launcher.skins import SkinLibrary,skin_bytes,upload_skin
from launcher.accounts import AccountRecord,offline_uuid
from launcher.seedmap import parse_seed,generate,VERSIONS


def png(width=64,height=64):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x80\x55\xcc\xff'*width)*height))+chunk(b'IEND',b'')


def test_schematic_folders_import_and_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp);root=base/'schematics';source=base/'test.litematic';source.write_bytes(b'schematic')
        assert scan_library(root)==[] and not root.exists()
        import_files(root,'department/builds',[source]);entries=scan_library(root)
        assert entries[0].directory and entries[0].path.name=='department'
        folder=root/'department/builds';item=scan_library(root,'department/builds')[0]
        assert item.path.read_bytes()==b'schematic'
        try:import_files(root,'department/builds',[source])
        except FileExistsError:pass
        else:raise AssertionError('must not overwrite')
        changed=rename_entry(root,item.path,'renamed.litematic');assert changed.exists()
        trash=remove_entry(root,changed);assert not changed.exists()
        restored=restore_recycled(trash,folder);assert restored.read_bytes()==b'schematic'


def test_file_library_rejects_escape_and_extension_changes():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)/'managed';root.mkdir();path=root/'a.litematic';path.write_bytes(b'a')
        for op in (lambda:checked_folder(root,'../escape'),lambda:rename_entry(root,path,'../b.litematic'),lambda:rename_entry(root,path,'a.exe'),lambda:remove_entry(root,root.parent/'outside')):
            try:op()
            except (PermissionError,ValueError):pass
            else:raise AssertionError('unsafe operation accepted')
        assert path.read_bytes()==b'a'


def test_screenshots_order_by_capture_time_and_hide_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name in ('2025-01-01_12.00.00.png','2026-01-01_12.00.00.png','ignored.txt'): (root/name).write_bytes(b'pic')
        (root/'.craftbridge-trash').mkdir()
        entries=scan_library(root,pictures=True)
        assert [p.path.name for p in entries]==['2026-01-01_12.00.00.png','2025-01-01_12.00.00.png']


def test_skin_library_isolated_selection_and_reset():
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp);source=base/'source.png';source.write_bytes(png());library=SkinLibrary(base)
        path=library.import_skin(source);assert path==library.import_skin(source)
        a=offline_uuid('PlayerOne');b=offline_uuid('PlayerTwo');library.select(a,path,'slim')
        assert library.selected(a)==(path,'slim') and library.selected(b) is None
        assert len(library.files())==1 and path.parent==base/'.onion/skins'
        library.reset(a);assert library.selected(a) is None and path.exists()


def test_skin_validation_and_online_only_upload():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'skin.png';path.write_bytes(png(32,32))
        try:skin_bytes(path)
        except ValueError:pass
        else:raise AssertionError('invalid dimensions accepted')
        path.write_bytes(png());account=AccountRecord('offline','Player',offline_uuid('Player'))
        with patch('launcher.skins.secure_open') as request:
            try:upload_skin(account,path,'classic')
            except ValueError:pass
            else:raise AssertionError('offline upload accepted')
            request.assert_not_called()


def test_skin_upload_multipart_and_safe_error():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'skin.png';path.write_bytes(png())
        account=AccountRecord('microsoft','Player',offline_uuid('Player'),access_token='test-placeholder',expires_at=10**12)
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch('launcher.skins.secure_open',return_value=Response()) as opener:
            upload_skin(account,path,'slim');request=opener.call_args.args[0]
            assert request.full_url=='https://api.minecraftservices.com/minecraft/profile/skins'
            assert request.get_header('Authorization')=='Bearer test-placeholder'
            assert b'name="variant"\r\n\r\nslim' in request.data and png() in request.data


def test_cape_profile_selection_and_offline_rejection():
    from launcher.skins import cape_profile,set_cape
    account=AccountRecord('microsoft','Player',offline_uuid('Player'),access_token='test-placeholder',expires_at=10**12)
    cape_id='e7dfea16-dc83-4a01-9be4-51d8ffe4a9d9'
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return json.dumps({'capes':[{'id':cape_id,'state':'ACTIVE'}]}).encode()
    with patch('launcher.skins.secure_open',return_value=Response()) as opener:
        assert cape_profile(account)['capes'][0]['id']==cape_id
        set_cape(account,cape_id);request=opener.call_args.args[0]
        assert request.get_method()=='PUT' and json.loads(request.data)=={'capeId':cape_id}
        set_cape(account,None);assert opener.call_args.args[0].get_method()=='DELETE'
        offline=AccountRecord('offline','Player',offline_uuid('Player'))
        try:set_cape(offline,None)
        except ValueError:pass
        else:raise AssertionError('offline cape sync accepted')


def test_cape_texture_restricts_hosts_and_size():
    from launcher.skins import texture_bytes
    with patch('launcher.network.fetch_public',return_value=png(64,32)) as fetch:
        assert texture_bytes('https://textures.minecraft.net/texture/example')==png(64,32)
        for url in ('http://textures.minecraft.net/texture/x','https://evil.example/x','https://textures.minecraft.net.evil.example/x'):
            try:texture_bytes(url)
            except ValueError:pass
            else:raise AssertionError('unsafe texture URL accepted')
        assert fetch.call_count==1


def test_cape_sync_checks_server_result_and_expired_account():
    from launcher.skins import sync_cape,cape_profile
    account=AccountRecord('microsoft','Player',offline_uuid('Player'),access_token='test-placeholder',expires_at=10**12)
    cape='e7dfea16-dc83-4a01-9be4-51d8ffe4a9d9'
    with patch('launcher.skins.set_cape',return_value={'capes':[{'id':cape,'state':'ACTIVE'}]}):
        assert sync_cape(account,cape)['capes'][0]['state']=='ACTIVE'
        try:sync_cape(account,None)
        except RuntimeError:pass
        else:raise AssertionError('unconfirmed cape change was reported successful')
    with patch('launcher.skins.set_cape',return_value={}),patch('launcher.skins.cape_profile',return_value={'capes':[]}) as profile:
        sync_cape(account,None);profile.assert_called_once_with(account)
    try:cape_profile(None)
    except ValueError:pass
    else:raise AssertionError('missing refreshed account accepted')


def test_cape_names_localize_known_aliases_and_keep_unknown_distinct():
    from launcher.skins import cape_name
    assert cape_name('Vanilla','')=='原版披风'
    assert cape_name('MCC 15th Year','')=='MCC 15 周年披风'
    assert cape_name('Minecon2012','')=='MINECON 2012 披风'
    assert cape_name('Future Cape','')=='Future Cape'
    assert cape_name(None,'e7dfea16-dc83-4a01-9be4-51d8ffe4a9d9')=='未命名披风 · e7dfea16'


def test_java_seed_parsing_and_unsupported_version():
    assert parse_seed('hello')==99162322 and parse_seed('-9223372036854775808')==-(1<<63)
    assert parse_seed('😀')==1772899
    try:generate('1','99.0')
    except ValueError:pass
    else:raise AssertionError('unsupported map version accepted')


def test_real_cubiomes_known_biome_and_determinism():
    # Upstream README's known example: seed 262, 1.18, origin is mushroom_fields.
    a=generate('262','1.18.2',scale=4,size=32,structures=False)
    b=generate('262','1.18.2',scale=4,size=32,structures=False)
    assert a.ids[16*32+16]==14 and a.legend[14]=='mushroom_fields'
    assert a.rgb==b.rgb and len(a.rgb)==32*32*3
    assert generate('1','1.20.6',dimension=-1,size=16,structures=False).ids


def test_modern_seedmap_263_new_biomes_are_generated():
    from launcher.seedmap import library
    native=library();seed=-3829811542736183482
    # Reference is pinned upstream tests/test_biomes.c: test_biomes_26_3.
    assert native.onion_biome_at(b'26.3',seed,0,68148,77,80990)==188
    new=generate(seed,'26.3',x=68148,z=80990,y=77,scale=4,size=32,structures=False)
    old=generate(seed,'26.2',x=68148,z=80990,y=77,scale=4,size=32,structures=False)
    assert 188 in new.ids and new.legend[188]=='dappled_forest' and 188 not in old.ids
    # Actual underground sample; version enum alone cannot produce this biome.
    caves=generate('0','26.2',x=-268,z=-444,y=-16,scale=4,size=32,structures=False)
    assert caves.ids[16*32+16]==187 and caves.legend[187]=='sulfur_caves'
    earlier=generate('0','26.1',x=-268,z=-444,y=-16,scale=4,size=32,structures=False)
    assert 187 not in earlier.ids


def test_modern_seedmap_263_end_ring_generation_change():
    from launcher.seedmap import library
    native=library();seed=856461443495910397
    # The fork's pinned End-ring regression changes from barrens to highlands.
    assert native.onion_biome_at(b'26.2',seed,1,-371136,64,-64)==43
    assert native.onion_biome_at(b'26.3',seed,1,-371136,64,-64)==42


def test_seedmap_all_declared_versions_and_dimensions():
    assert VERSIONS[0]=='26.3'
    for version in VERSIONS:
        for dimension in (-1,0,1):
            data=generate('12345',version,dimension=dimension,size=16,structures=False)
            assert len(data.rgb)==16*16*3 and len(data.ids)==256


def test_offline_skin_loopback_profile_and_signature():
    from launcher.offline_skin import OfflineSkinServer
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'skin.png';path.write_bytes(png());account=AccountRecord('offline','Player',offline_uuid('Player'))
        server=OfflineSkinServer(account,path,'slim')
        try:
            # Explicitly bypass environmental proxies for this local-only test.
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(server.url) as response:meta=json.load(response)
            with opener.open(server.url+'sessionserver/session/minecraft/profile/'+account.uuid.replace('-','')) as response:profile=json.load(response)
            assert profile['id']==account.uuid.replace('-','')
            prop=profile['properties'][0];texture=json.loads(base64.b64decode(prop['value']))
            assert texture['textures']['SKIN']['metadata']['model']=='slim'
            with opener.open(texture['textures']['SKIN']['url']) as response:assert response.read()==png()
            public=base64.b64decode(''.join(meta['signaturePublickey'].splitlines()[1:-1]))
            def der(data,offset=0):
                tag=data[offset];length=data[offset+1];start=offset+2
                if length&128:
                    count=length&127;length=int.from_bytes(data[start:start+count],'big');start+=count
                return tag,data[start:start+length],start+length
            _,sequence,_=der(public);_,_,offset=der(sequence);_,bits,_=der(sequence,offset)
            _,rsa,_=der(bits[1:]);_,modulus,offset=der(rsa);_,exponent,_=der(rsa,offset)
            n=int.from_bytes(modulus,'big');e=int.from_bytes(exponent,'big')
            signed=pow(int.from_bytes(base64.b64decode(prop['signature']),'big'),e,n).to_bytes((n.bit_length()+7)//8,'big')
            assert signed.endswith(hashlib.sha1(prop['value'].encode()).digest())
            assert server.server.server_address[0]=='127.0.0.1'
        finally:server.close()
