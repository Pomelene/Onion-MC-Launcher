"""Build configured launcher editions from explicit, project-relative manifests."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name('config.json')


def inside(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('Expected a relative path: '+str(value))
    path = (root/value).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('Path escapes its allowed directory: '+value)
    return path


def discover(root, config):
    source = set(config['entry_files'])
    for name in config['source_roots']:
        directory = inside(root, name)
        for path in directory.rglob('*.py'):
            if '__pycache__' not in path.parts:
                source.add(path.relative_to(root).as_posix())
    overlay_root = inside(root, config['overlay_root'])
    overlay = {p.relative_to(root).as_posix() for p in overlay_root.rglob('*.py')
               if '__pycache__' not in p.parts}
    return sorted(source), sorted(overlay)


def validate(root, config):
    if config.get('schema') != 1:
        raise ValueError('Unsupported configuration schema')
    if config.get('edition') not in ('standard', 'thunion', 'both'):
        raise ValueError('edition must be standard, thunion or both')
    actual, overlays = discover(root, config)
    for key, expected in (('source_files', actual), ('overlay_files', overlays)):
        listed = config[key]
        if len(set(listed)) != len(listed):
            raise ValueError('Duplicate files in '+key)
        missing = sorted(set(listed)-set(expected))
        added = sorted(set(expected)-set(listed))
        if missing or added:
            raise ValueError(f'{key} is out of date. Removed: {missing}; Added: {added}. '
                             'Review changes, then run --refresh-manifest.')
    for name in config['source_files']+config['overlay_files']+config['include_files']:
        path = inside(root, name)
        if not path.is_file():raise ValueError('Missing required file: '+name)
        if path.suffix.lower() in ('.key', '.pem', '.pfx', '.p12') or path.name in ('onionmcl.json','accounts.json','settings.json'):
            raise ValueError('User data or private key in manifest: '+name)
    inside(root, config['dependencies'])
    inside(root, config['output_dir'])
    overlay_root = inside(root, config['overlay_root'])
    destinations = set(config['source_files'])
    for name in config['overlay_files']:
        target = inside(root, name).relative_to(overlay_root).as_posix()
        if target in destinations and inside(root,target).read_bytes()!=inside(root,name).read_bytes():
            raise ValueError('Overlay differs from edition source; update the canonical overlay first: '+target)
        destinations.add(target)


def version_from(root):
    tree = ast.parse((root/'launcher/paths.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='LAUNCHER_VERSION' for t in node.targets):
            version = ast.literal_eval(node.value).removesuffix('-T')
            if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', version):break
            return version
    raise ValueError('Unable to read LAUNCHER_VERSION')


def stage(root, config, edition, destination):
    destination = destination.resolve()
    version = version_from(root)+('-T' if edition=='thunion' else '')
    for name in dict.fromkeys(config['source_files']+config['include_files']):
        target = inside(destination, name);target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inside(root, name), target)
    if edition=='thunion':
        overlay_root = inside(root, config['overlay_root'])
        for name in config['overlay_files']:
            source = inside(root, name)
            target = inside(destination, source.relative_to(overlay_root).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True);shutil.copy2(source, target)
    paths = destination/'launcher/paths.py'
    content, count = re.subn(r'^LAUNCHER_VERSION\s*=.*$', 'LAUNCHER_VERSION = '+repr(version),
                             paths.read_text(encoding='utf-8'), flags=re.MULTILINE)
    if count != 1:raise ValueError('Expected exactly one version assignment')
    paths.write_text(content, encoding='utf-8')
    metadata = destination/'packaging/windows-version.txt'
    text = metadata.read_text(encoding='utf-8')
    numbers = tuple(int(v) for v in version.removesuffix('-T').split('.'))
    numbers = numbers+(0,)*(4-len(numbers))
    text = re.sub(r'(filevers|prodvers)=\([^)]*\)', lambda m:m[1]+'='+repr(numbers), text)
    text = re.sub(r"(StringStruct\('(FileVersion|ProductVersion)',\s*)'[^']*'", lambda m:m[1]+repr(version), text)
    metadata.write_text(text, encoding='utf-8')
    (destination/'packaging/build-profile.json').write_text(json.dumps({'edition':edition}), encoding='utf-8')
    (destination/'tmp').mkdir(exist_ok=True);(destination/'docs').mkdir(exist_ok=True)
    # Compile the staged files before invoking a costly native build.
    for file in (destination/'launcher').rglob('*.py'):
        compile(file.read_text(encoding='utf-8'), str(file), 'exec')
    return version


def build(root, config, edition):
    cache = root/'tmp/automatic-builds';cache.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=edition+'-', dir=cache))
    version = stage(root, config, edition, directory)
    output = f'Onion-v{version}.exe'
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell:raise RuntimeError('PowerShell is required for Windows builds')
    environment = dict(os.environ)
    # Invoke the same interpreter that started this script, even outside the project.
    environment['PATH']=str(Path(sys.executable).parent)+os.pathsep+environment.get('PATH','')
    command = [shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(directory/'scripts/build_qt.ps1'),
               '-OutputName',output,'-DependenciesPath',str(inside(root, config['dependencies']))]
    log = directory/'build.log'
    print(f'Building {edition} {version}\nLog: {log}', flush=True)
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=directory, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Build failed; existing executable retained. See '+str(log))
    source = directory/'release'/output
    output_dir = inside(root, config['output_dir']);output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    temporary = output_dir/(output+'.building')
    try:
        shutil.copyfile(source, temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=digest:raise RuntimeError('Copy checksum mismatch')
        os.replace(temporary, output_dir/output)
    finally:
        if temporary.is_file():temporary.unlink()
    reports = ['qt-startup-check.json','qt-frozen-check.json','qt-windows-raster-check.json','bundle-audit.json']
    if edition=='thunion':reports.append('thunion-frozen-web-check.json')
    print('Ready: '+str(output_dir/output), flush=True)
    return {'edition':edition,'version':version,'exe':str(output_dir/output),'sha256':digest,
            'reports':{name:str(directory/'docs'/name) for name in reports},'log':str(log)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=DEFAULT_CONFIG)
    parser.add_argument('--edition',choices=('standard','thunion','both'),help='Override edition for this run')
    parser.add_argument('--check',action='store_true',help='Validate manifests without building')
    parser.add_argument('--refresh-manifest',action='store_true',help='Update source lists without building')
    args = parser.parse_args();path = args.config.resolve()
    config = json.loads(path.read_text(encoding='utf-8'))
    if args.refresh_manifest:
        config['source_files'],config['overlay_files']=discover(ROOT,config)
        path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Updated source manifest: '+str(path));return 0
    if args.edition:config['edition']=args.edition
    validate(ROOT, config)
    if args.check:print('Configuration and source manifests are valid.');return 0
    editions=('standard','thunion') if config['edition']=='both' else (config['edition'],)
    results=[build(ROOT, config, edition) for edition in editions]
    report=ROOT/'tmp/automatic-builds/latest.json'
    report.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,RuntimeError,OSError,KeyError) as error:
        print('ERROR: '+str(error),file=sys.stderr);sys.exit(1)
