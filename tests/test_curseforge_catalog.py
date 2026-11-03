from types import SimpleNamespace
from launcher.curseforge import CurseForgeClient,resolve_required_versions,CurseForgeError
from launcher.catalog import pick_version

def test_curseforge_search_versions_and_required_dependencies():
    files={1:[{'id':11,'displayName':'Main','fileName':'main.jar','fileLength':8,'gameVersions':['1.20.1','Fabric'],'downloadUrl':'https://cdn.example/main.jar','hashes':[{'algo':1,'value':'a'*40}],'dependencies':[{'modId':2,'relationType':3}]}],
           2:[{'id':22,'displayName':'Library','fileName':'lib.jar','fileLength':8,'gameVersions':['1.20.1','Fabric'],'downloadUrl':'https://cdn.example/lib.jar','hashes':[{'algo':1,'value':'b'*40}]}]}
    class Downloader:
        def fetch_json(self,url,headers=None):
            if '/mods/search?' in url:return {'data':[{'id':1,'name':'Main','summary':'Example'}],'pagination':{'totalCount':1}}
            return {'data':files[int(url.split('/mods/')[1].split('/')[0])]}
    client=CurseForgeClient(Downloader());hits=client.search('mod','main','1.20.1','fabric')
    assert hits['hits'][0]['project_id']=='cf:1' and hits['total_hits']==1
    root=pick_version(client.normalized_versions(1),'1.20.1','fabric');assert root
    assert [v['project_id'] for v in resolve_required_versions(client.downloader,'',root,'1.20.1','fabric')]==['cf:2','cf:1']
    files[2][0]['downloadUrl']=None
    try:resolve_required_versions(client.downloader,'',root,'1.20.1','fabric')
    except CurseForgeError:pass
    else:raise AssertionError('Restricted dependency must not be silently installed')
