"""Manifest drift and edition staging must fail safely before native packaging."""
import copy
import json
from pathlib import Path
import runpy
import tempfile

ROOT=Path(__file__).resolve().parents[1]
API=runpy.run_path(str(ROOT/'build_tools/build.py'))


def test_build_manifest_rejects_added_deleted_and_escape_paths():
    config=json.loads((ROOT/'build_tools/config.json').read_text(encoding='utf-8'))
    API['validate'](ROOT,config)
    for altered in (dict(config,source_files=config['source_files'][:-1]),
                    dict(config,source_files=config['source_files']+['launcher/deleted.py'])):
        try:API['validate'](ROOT,altered)
        except ValueError:pass
        else:raise AssertionError('Out-of-date source manifest accepted')
    for path in ('../outside','../../outside','C:/outside'):
        try:API['inside'](ROOT,path)
        except ValueError:pass
        else:raise AssertionError('Escaping path accepted')


def test_edition_staging_preserves_source_and_excludes_personal_files():
    config=json.loads((ROOT/'build_tools/config.json').read_text(encoding='utf-8'))
    original=(ROOT/'launcher/paths.py').read_bytes()
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='edition-staging-') as folder:
        for edition in ('standard','thunion'):
            target=Path(folder)/edition;target.mkdir()
            version=API['stage'](ROOT,config,edition,target)
            assert version.endswith('-T')==(edition=='thunion')
            assert (target/'launcher/club_services.py').exists()==(edition=='thunion')
            assert (target/'launcher/qtui/i18n_en.py').exists()
            assert json.loads((target/'packaging/build-profile.json').read_text())['edition']==edition
            assert not (target/'onionmcl.json').exists()
            assert not (target/'config').exists()
            assert version in (target/'packaging/windows-version.txt').read_text()
    assert (ROOT/'launcher/paths.py').read_bytes()==original
