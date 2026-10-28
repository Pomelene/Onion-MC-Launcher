"""Compare deterministic local workloads against a Git revision, without game writes.

Network timing uses a simulated fixed 10 ms service latency, not Internet claims.
Example: python scripts/benchmark_optimizations.py --baseline e219ced --output docs/performance-20261028.json
"""
import argparse,hashlib,importlib.util,json,statistics,subprocess,sys,tempfile,time,tracemalloc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher import assets,download,mods,mod_plan,java,natives


def baseline(ref,name):
    key='launcher._benchmark_'+name.replace('/','_')
    source=subprocess.check_output(['git','show',ref+':launcher/'+name+'.py'],cwd=ROOT)
    spec=importlib.util.spec_from_loader(key,loader=None)
    module=importlib.util.module_from_spec(spec);sys.modules[key]=module
    exec(compile(source,key,'exec'),module.__dict__)
    return module


def median(work,rounds=5):
    values=[]
    for _ in range(rounds):
        start=time.perf_counter();work();values.append((time.perf_counter()-start)*1000)
    return statistics.median(values)


def run(ref):
    before={name:baseline(ref,name) for name in ('assets','download','mods','mod_plan','java','natives')}
    before['icons']=baseline(ref,'qtui/content_icons')
    from launcher.qtui.content_icons import read_content_icon
    report={'baseline_ref':ref,'workloads':[],'network':'Simulated fixed 10 ms per request; no real network throughput claim'}
    def record(name,old,new,unit='ms',**extra):
        item={'name':name,'baseline':round(old,3),'optimized':round(new,3),'unit':unit,
              'reduction_percent':round((old-new)/old*100,2),'speedup':round(old/new,3),**extra}
        report['workloads'].append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='perf-bench-') as folder:
        root=Path(folder);objects=root/'objects';objects.mkdir();data={'objects':{}}
        for index in range(6000):
            digest=hashlib.sha1(str(index).encode()).hexdigest();target=objects/digest[:2]/digest;target.parent.mkdir(exist_ok=True);target.write_bytes(b'asset')
            data['objects'][str(index)]={'hash':digest,'size':5}
        old=before['assets'].AssetIndex.parse(data);new=assets.AssetIndex.parse(data)
        assert old.jobs(objects)==new.jobs(objects)==[]
        record('asset_presence_6000',median(lambda:old.jobs(objects)),median(lambda:new.jobs(objects)),objects=6000)

        import io,zipfile
        modroot=root/'mods';modroot.mkdir()
        for index in range(200):
            with zipfile.ZipFile(modroot/(str(index)+'.jar'),'w',zipfile.ZIP_DEFLATED) as out:
                out.writestr('fabric.mod.json',json.dumps({'id':'mod'+str(index),'name':'Mod '+str(index),'version':'1.0'}))
        old_result=before['mods'].scan_mods(modroot);new_result=mods.scan_mods(modroot)
        assert [(p.path,p.name,p.mod_id,p.version) for p in old_result]==[(p.path,p.name,p.mod_id,p.version) for p in new_result]
        record('mod_list_repeat_200',median(lambda:before['mods'].scan_mods(modroot)),median(lambda:mods.scan_mods(modroot)),mods=200)
        def list_with_icons(scanner,reader):return [(info.name,reader(info.path)) for info in scanner(modroot)]
        expected=list_with_icons(before['mods'].scan_mods,before['icons'].read_content_icon)
        assert expected==list_with_icons(mods.scan_mods,read_content_icon)
        record('mod_list_metadata_and_icons_200',median(lambda:list_with_icons(before['mods'].scan_mods,before['icons'].read_content_icon)),median(lambda:list_with_icons(mods.scan_mods,read_content_icon)),mods=200,scope='filesystem and metadata only; excludes Qt paint')

        versions=[]
        for index,path in enumerate(sorted(modroot.glob('*.jar'))):
            digest=hashlib.sha1(path.read_bytes()).hexdigest();key='project'+str(index)
            base={'project_id':key,'game_versions':['1.21.1'],'loaders':['fabric'],'version_type':'release','files':[{'hashes':{'sha1':digest},'filename':path.name}],'id':key+'-1','date_published':'2025-01-01'}
            versions.extend([base,{**base,'id':key+'-2','date_published':'2026-01-01'}])
        class Remote:
            threads=8
            def __init__(self):self.calls=0
            def fetch_json(self,url):
                self.calls+=1;time.sleep(.01)
                if '/version_file/' in url:
                    digest=url.split('/version_file/')[1].split('?')[0]
                    return next(v for v in versions if v['files'][0]['hashes']['sha1']==digest)
                key=url.split('/project/')[1].split('/')[0]
                return [v for v in versions if v['project_id']==key]
        class Batch(Remote):
            def post_json(self,url,payload):
                self.calls+=1;time.sleep(.01);result={}
                for digest in payload['hashes']:
                    matches=[v for v in versions if v['files'][0]['hashes']['sha1']==digest]
                    if matches:result[digest]=matches[-1] if url.endswith('/update') else matches[0]
                return result
        original=Remote();optimized=Batch()
        old_time=median(lambda:before['mod_plan'].updates(original,modroot,'1.21.1','fabric'),3)
        new_time=median(lambda:mod_plan.updates(optimized,modroot,'1.21.1','fabric'),3)
        assert before['mod_plan'].updates(Remote(),modroot,'1.21.1','fabric')==mod_plan.updates(Batch(),modroot,'1.21.1','fabric')
        record('mod_update_fixed_latency_200',old_time,new_time,requests_before=original.calls//3,requests_after=optimized.calls//3)

        payload=root/'large.bin';payload.write_bytes(b'onion-content\0'*(2*1024*1024))
        body=payload.read_bytes();job=download.DownloadJob('https://example.invalid',payload,sha1=hashlib.sha1(body).hexdigest(),sha256=hashlib.sha256(body).hexdigest(),size=len(body))
        assert before['download'].Downloader._hash_valid(payload,job) and download.Downloader._hash_valid(payload,job)
        record('dual_hash_local_file',median(lambda:before['download'].Downloader._hash_valid(payload,job)),median(lambda:download.Downloader._hash_valid(payload,job)),bytes=len(body))

        from tests.harness import FakeServer
        server=FakeServer({'/large':body}).start()
        try:
            counter=[0]
            def transfer(base):
                counter[0]+=1;path=root/('download-'+str(counter[0]))
                task=download.DownloadJob(server.url('/large'),path,sha1=job.sha1,sha256=job.sha256,size=len(body))
                assert base(retries=1,use_system_proxy=False).download_one(task)
                assert path.stat().st_size==len(body);path.unlink()
            record('verified_download_loopback',median(lambda:transfer(before['download'].Downloader),3),median(lambda:transfer(download.Downloader),3),bytes=len(body))
        finally:server.stop()

        def queue_peak(base):
            class Local(base):
                def download_one(self,job):return True
            jobs=[download.DownloadJob('https://example.invalid',root/str(i)) for i in range(10000)]
            tracemalloc.start();ok,failed=Local(threads=4).download_many(jobs)
            peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
            assert len(ok)==len(jobs) and not failed
            return peak
        record('download_queue_peak_10000',queue_peak(before['download'].Downloader),queue_peak(download.Downloader),unit='bytes')
        import os
        from launcher.libraries import Library
        source=root/'native.jar';destination=root/'natives';content=(os.urandom(128*1024)+b'\0'*(128*1024))*8
        with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as archive:
            for index in range(6):archive.writestr(str(index)+'.dll',content)
        library=Library.from_json({'name':'org.fixture:native:1'})
        natives.extract_native(library,source,destination)
        record('native_preparation_repeat_12MiB',median(lambda:before['natives'].extract_native(library,source,destination),3),median(lambda:natives.extract_native(library,source,destination),3),bytes=len(content)*6)
        assert all(hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(content).digest() for path in destination.iterdir())
    original_paths=before['java']._candidate_paths();new_paths=java._candidate_paths()
    assert set(original_paths)==set(new_paths),'Java discovery results changed'
    record('java_path_discovery',median(lambda:before['java']._candidate_paths(),3),median(lambda:java._candidate_paths(),3),runtimes=len(new_paths))
    old_downloader=before['download'].Downloader();new_downloader=download.Downloader();new_downloader._opener()
    record('https_request_setup',median(old_downloader._opener,10),median(new_downloader._opener,10))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=run(args.baseline);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
