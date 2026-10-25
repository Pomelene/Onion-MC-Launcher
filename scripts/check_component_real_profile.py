"""Opt-in network check on a copy of a profile; source game data is read-only."""
import hashlib,json,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher.config import Config
from launcher.repository import GameRepository
from launcher.components import component_info,replace_loader
from launcher.download import Downloader

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    source=Path(sys.argv[1]);vid=source.name;original={p:digest(p) for p in (source/(vid+'.json'),source/(vid+'.jar'))}
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='real-component-') as tmp:
        base=Path(tmp);config=Config(base/'onionmcl.json');config.update(dict(game_dir=str(base/'game'),reference_roots=[str(source.parent.parent)]))
        repo=GameRepository(config,Downloader(retries=1,timeout=20));target=repo.version_dir(vid);target.mkdir(parents=True)
        for path in original:shutil.copy2(path,target/path.name)
        for rel in ('mods/keep.jar','saves/keep/level.dat','config/keep.json','options.txt'):
            path=target/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('unchanged')
        game,kind,current=component_info(repo,vid);assert kind=='fabric'
        chosen='0.19.4' if current!='0.19.4' else '0.19.5'
        replace_loader(repo,vid,kind,chosen,on_stage=print,expected_game=game)
        assert component_info(repo,vid)==(game,kind,chosen) and repo.list_installed()==[vid]
        assert original=={p:digest(p) for p in original}
        assert digest(target/(vid+'.jar'))==original[source/(vid+'.jar')]
        assert all((target/rel).read_text()=='unchanged' for rel in ('mods/keep.jar','saves/keep/level.dat','config/keep.json','options.txt'))
        libraries=repo.resolver.resolve(vid).libraries
        assert [lib.name for lib in libraries if lib.name.startswith('net.fabricmc:fabric-loader:')]==['net.fabricmc:fabric-loader:'+chosen]
        assert all(repo.resolve_library_file(lib)[0] for lib in libraries if lib.name.startswith(('net.fabricmc:','org.ow2.asm:')))
        print(json.dumps(dict(result='pass',game=game,old=current,new=chosen,instances=repo.list_installed(),source_unchanged=True,network=True)))
if __name__=='__main__':main()
