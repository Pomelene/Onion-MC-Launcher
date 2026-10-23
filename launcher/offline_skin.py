"""Ephemeral loopback-only skin endpoint for one offline account.

An unsigned offline identity is never used to authenticate with Mojang. The
ephemeral RSA key signs texture properties only for the local injector session.
"""
import base64
import hashlib
import json
import math
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .skins import skin_bytes


def _prime(bits):
    while True:
        n=secrets.randbits(bits)|(1<<(bits-1))|1
        if any(n%p==0 for p in (3,5,7,11,13,17,19,23,29,31,37)):continue
        d=n-1;s=0
        while d%2==0:d//=2;s+=1
        for _ in range(20):
            a=secrets.randbelow(n-3)+2;x=pow(a,d,n)
            if x in (1,n-1):continue
            for _ in range(s-1):
                x=pow(x,2,n)
                if x==n-1:break
            else:break
        else:return n


def _der(tag,data):
    size=len(data);length=bytes([size]) if size<128 else bytes([128+(size.bit_length()+7)//8])+size.to_bytes((size.bit_length()+7)//8,'big')
    return bytes([tag])+length+data


def _integer(value):
    data=value.to_bytes((value.bit_length()+7)//8,'big')
    return _der(2,b'\0'+data if data[0]&128 else data)


def _key():
    while True:
        p=_prime(1024);q=_prime(1024);phi=(p-1)*(q-1)
        if p!=q and math.gcd(65537,phi)==1:break
    n=p*q;d=pow(65537,-1,phi)
    public=_der(0x30,bytes.fromhex('300d06092a864886f70d0101010500')+_der(3,b'\0'+_der(0x30,_integer(n)+_integer(65537))))
    text=base64.b64encode(public).decode()
    pem='-----BEGIN PUBLIC KEY-----\n'+'\n'.join(text[i:i+64] for i in range(0,len(text),64))+'\n-----END PUBLIC KEY-----'
    def sign(message):
        digest=bytes.fromhex('3021300906052b0e03021a05000414')+hashlib.sha1(message).digest()
        size=(n.bit_length()+7)//8;encoded=b'\0\1'+b'\xff'*(size-len(digest)-3)+b'\0'+digest
        return base64.b64encode(pow(int.from_bytes(encoded,'big'),d,n).to_bytes(size,'big')).decode()
    return pem,sign


class OfflineSkinServer:
    def __init__(self,account,path,variant):
        if account.type!='offline':raise ValueError('本地皮肤端点仅用于离线账户')
        self.data=skin_bytes(path);self.secret=secrets.token_urlsafe(24)
        public,sign=_key();owner=self;uid=account.uuid.replace('-','')
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,data=None,kind='application/json'):
                body=b'' if data is None else data if isinstance(data,bytes) else json.dumps(data).encode()
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
            def do_GET(self):
                # Host and unguessable root prevent a website from accessing the local endpoint.
                if self.headers.get('Host')!=f'127.0.0.1:{owner.server.server_port}':self.reply(403);return
                path=urllib.parse.urlsplit(self.path).path
                if path==f'/{owner.secret}/':
                    self.reply(200,{'meta':{'serverName':'Onion Local Skin','implementationName':'Onion','feature.non_email_login':True},
                        'skinDomains':['127.0.0.1'],'signaturePublickey':public})
                elif path==f'/{owner.secret}/textures/skin.png':self.reply(200,owner.data,'image/png')
                elif path==f'/{owner.secret}/sessionserver/session/minecraft/profile/{uid}':
                    texture={'profileId':uid,'profileName':account.username,'textures':{'SKIN':{'url':owner.url+'textures/skin.png','metadata':{'model':variant}}}}
                    value=base64.b64encode(json.dumps(texture,separators=(',',':')).encode()).decode()
                    self.reply(200,{'id':uid,'name':account.username,'properties':[{'name':'textures','value':value,'signature':sign(value.encode())}]})
                else:self.reply(404)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.url=f'http://127.0.0.1:{self.server.server_port}/{self.secret}/'
        self.thread=threading.Thread(target=self.server.serve_forever,name='OnionLocalSkin',daemon=True);self.thread.start()

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
