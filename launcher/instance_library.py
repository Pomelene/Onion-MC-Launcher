"""Read-only cross-root instance enumeration with directory-scoped metadata."""
from pathlib import Path
from types import SimpleNamespace
from .version import VersionResolver
from .instance import InstanceStore
from .modpack import _base_version,_detect_loader
from .game_libraries import GameLibraries
from .storage import directory_key


def collect(entries,metadata_path,legacy_root=None,cancel=None):
    rows=[];unavailable=[]
    for entry in entries:
        if cancel and cancel.is_set():break
        root=Path(entry['path'])
        try:
            if not root.is_dir():unavailable.append(str(root));continue
            resolver=VersionResolver(root/'versions');repo=SimpleNamespace(resolver=resolver)
            store=InstanceStore(metadata_path,root,legacy_root)
            for vid in resolver.list_installed():
                if cancel and cancel.is_set():break
                meta=store.get(vid);loader,_=_detect_loader(repo,vid)
                rows.append(dict(key=(directory_key(root),vid),root=str(root),library=GameLibraries.title(entry),id=vid,
                    name=meta.display_name,game=_base_version(repo,vid),loader=loader or '原版',favorite=meta.favorite,tags=meta.tags,last_played=meta.last_played))
        except (OSError,ValueError):unavailable.append(str(root))
    return rows,unavailable
