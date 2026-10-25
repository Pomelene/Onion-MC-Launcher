"""Bounded local task records. No accounts, tokens or executable retry commands."""
import json,time,uuid,math
from pathlib import Path
from .safety import contained,write_text
from .crash import redact


class TaskHistory:
    def __init__(self,root):
        self.root=Path(root);self.path=self.root/'.onion/tasks/history.json';self.items=[];self.live={};self.retries={}
        try:
            contained(self.path,self.root)
            if self.path.stat().st_size<=1024**2:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(data,list):
                    for value in data[-100:]:
                        if not isinstance(value,dict) or not isinstance(value.get('id'),str):continue
                        if value.get('state') not in ('running','cancelling','complete','failed','cancelled','interrupted'):continue
                        try:
                            started=float(value.get('started',0));finished=float(value.get('finished',0));received=max(0,min(2**50,int(value.get('bytes',0))))
                            if not math.isfinite(started) or not math.isfinite(finished):continue
                            started=max(0,min(time.time()+86400,started));finished=max(0,min(time.time()+86400,finished))
                        except (ValueError,TypeError,OverflowError):continue
                        self.items.append(dict(id=value['id'][:64],title=str(value.get('title','任务'))[:180],library=str(value.get('library',''))[:1000],instance=str(value.get('instance',''))[:256],state=value['state'],started=started,finished=finished,bytes=received,progress=str(value.get('progress',''))[:100],detail=redact(str(value.get('detail','')))[:1000]))
        except (OSError,ValueError):pass
        for item in self.items:
            if item.get('state') in ('running','cancelling'):item['state']='interrupted';item['detail']='上次运行未正常结束；请重新发起原操作'

    def save(self):
        contained(self.path,self.root);self.path.parent.mkdir(parents=True,exist_ok=True)
        write_text(self.path,json.dumps(self.items[-100:],ensure_ascii=False,indent=2))

    def begin(self,title,library,instance):
        item=dict(id=uuid.uuid4().hex,title=str(title)[:180],library=str(library),instance=str(instance),state='running',started=time.time(),finished=0,detail='准备中',bytes=0,progress='')
        self.items.append(item)
        # Do not discard an active task when pruning old history.
        if len(self.items)>100:
            old=next((v for v in self.items if v['state'] not in ('running','cancelling')),None)
            if old:self.items.remove(old);self.retries.pop(old['id'],None)
        self._persist();return item

    def progress(self,item,value):
        if isinstance(value,str):item['detail']=redact(value)[:500];item['progress']=''
        elif isinstance(value,tuple) and len(value)==2:
            done,total=value;item['progress']=f'{done:,} / {total:,}' if total>0 else ''
        elif isinstance(value,dict) and value.get('kind')=='transfer':item['bytes']=max(item['bytes'],int(value.get('bytes',0)))

    def finish(self,item,state,detail=''):
        item.update(state=state,finished=time.time());self.live.pop(item['id'],None)
        if detail:item['detail']=redact(str(detail))[:1000]
        self._persist()

    def _persist(self):
        # A read-only portable folder must not turn a successful game task into a failure.
        try:self.save()
        except OSError:pass

    def clear_finished(self):
        self.items=[v for v in self.items if v.get('state') in ('running','cancelling')]
        self.retries={k:v for k,v in self.retries.items() if k in self.live};self._persist()
