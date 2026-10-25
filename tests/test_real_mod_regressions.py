"""Regressions model merged launcher profiles and real-world Fabric packaging."""
import io,json,tempfile,zipfile
from pathlib import Path
from launcher.version import VersionResolver
from launcher.mod_audit import audit,inspect_jar,matches
from tests.test_next_features import jar


def bundle(key,depends,entries):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('fabric.mod.json',json.dumps(dict(id=key,version='1.0',depends=depends,jars=[dict(file='META-INF/jars/'+name) for name in entries])))
        for name,data in entries.items():archive.writestr('META-INF/jars/'+name,data)
    return out.getvalue()


def test_merged_profile_uses_client_metadata_not_instance_name():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);vid='custom-name-with-no-version';folder=root/vid;folder.mkdir()
        (folder/(vid+'.json')).write_text(json.dumps(dict(id=vid,mainClass='Main',libraries=[])))
        with zipfile.ZipFile(folder/(vid+'.jar'),'w') as archive:archive.writestr('version.json',json.dumps(dict(id='26.3',name='26.3',java_version=25)))
        resolved=VersionResolver(root).resolve(vid)
        assert resolved.game_version=='26.3' and resolved.java_major==25
        assert resolved.game_version_source=='客户端 JAR / version.json'


def test_instance_name_is_not_a_game_version_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);vid='26.3-Fabric-custom';folder=root/vid;folder.mkdir()
        (folder/(vid+'.json')).write_text(json.dumps(dict(id=vid,mainClass='Main',libraries=[])))
        assert VersionResolver(root).resolve(vid).game_version==''


def test_valid_control_characters_in_description_are_not_corrupt_mods():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        with zipfile.ZipFile(root/'description.jar','w') as archive:archive.writestr('fabric.mod.json','{"id":"valid_mod","version":"1.0","description":"first line\nsecond line"}')
        assert inspect_jar(root/'description.jar')[0].id=='valid_mod'
        assert not audit(root)
        with zipfile.ZipFile(root/'broken.jar','w') as archive:archive.writestr('fabric.mod.json','{"id":')
        assert any(item.code=='metadata' for item in audit(root))


def test_shared_nested_libraries_are_candidates_not_duplicate_root_mods():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/'api.jar').write_bytes(bundle('api',{},dict(library=jar('shared','2.0'))))
        (root/'renderer.jar').write_bytes(bundle('renderer',{'shared':'>=1'},dict(library=jar('shared','1.0'))))
        (root/'consumer.jar').write_bytes(jar('consumer',depends={'shared':'>=2'}))
        assert not audit(root,loader='fabric')
        (root/'consumer.jar').write_bytes(jar('consumer',depends={'shared':'>=3'}))
        assert any(item.code=='version' for item in audit(root,loader='fabric'))
        assert not any(item.code=='duplicate' for item in audit(root,loader='fabric'))


def test_loader_supplied_nested_dependency_satisfies_mod_requirements():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);mods=root/'mods';mods.mkdir()
        (mods/'client.jar').write_bytes(jar('client',depends={'mixinextras':'>=0.5.5'}))
        (mods/'older-bundle.jar').write_bytes(bundle('old_bundle',{},dict(extra=jar('mixinextras','0.4.1'))))
        runtime=root/'fabric-loader.jar';runtime.write_bytes(bundle('fabricloader',{},dict(extra=jar('mixinextras','0.5.5'))))
        assert not audit(mods,loader='fabric',loader_version='0.19.5',runtime_mods=[runtime])


def test_large_but_valid_nested_dictionary_does_not_exceed_old_eight_mb_limit():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);nested=io.BytesIO()
        with zipfile.ZipFile(nested,'w',zipfile.ZIP_STORED) as archive:
            archive.writestr('fabric.mod.json',json.dumps(dict(id='dictionary',version='0.9.0')))
            archive.writestr('dictionary.dat',b'x'*(9*1024**2))
        (root/'notebot.jar').write_bytes(bundle('notebot',{'dictionary':'*'},dict(dictionary=nested.getvalue())))
        assert not audit(root,loader='fabric')


def test_server_only_mod_is_ignored_on_client_without_unknown_metadata_warning():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'server.jar').write_bytes(jar('server',depends={'missing_server':'*'},extra={'environment':'server'}))
        assert not audit(root,loader='fabric')


def test_fabric_empty_prerelease_and_modern_version_predicates():
    assert matches('26.3','>=26.3-') is True
    assert matches('26.3','~26.3-') is True
    assert matches('26.3','26.3.x') is True
    assert matches('26.3-beta.1','>=26.3-') is True
    assert matches('26.4-beta.1','~26.3-') is False
    assert matches('26.3','>=26.2-') is True


def test_nested_candidate_selection_satisfies_constraints_not_just_highest_version():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/'api.jar').write_bytes(bundle('api',{},dict(one=jar('shared','1.5'),two=jar('shared','2.0'))))
        (root/'consumer.jar').write_bytes(jar('consumer',depends={'shared':'>=1 <2'}))
        assert not audit(root,loader='fabric')


def test_deeply_nested_required_dependency_activates_parent_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);middle=bundle('middle',{},dict(deep=jar('deep','1.0')))
        (root/'api.jar').write_bytes(bundle('api',{},dict(middle=middle)))
        (root/'consumer.jar').write_bytes(jar('consumer',depends={'deep':'>=1'}))
        assert not audit(root,loader='fabric')
