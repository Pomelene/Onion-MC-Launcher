"""Local cubiomes adapter: explicit supported versions, no network or approximations."""
import ctypes
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

VERSIONS = ['26.3','26.2','26.1','1.21.11','1.21.9','1.21.6','1.21.5','1.21.4','1.21.3','1.21.1','1.20.6','1.19.4','1.19.2','1.18.2','1.17.1','1.16.5','1.15.2','1.14.4','1.13.2','1.12.2','1.8.9','1.7.10']
STRUCTURES = ['村庄','沙漠神殿','丛林神庙','女巫小屋','海底神殿','林地府邸','掠夺者前哨站','远古城市','下界要塞','堡垒遗迹','末地城','试炼密室','废弃营地']


def parse_seed(text):
    text = str(text).strip()
    if not text: raise ValueError('请输入世界种子')
    try:
        value=int(text)
        if -(1<<63)<=value<(1<<63): return value
    except ValueError: pass
    # Java String.hashCode works on UTF-16 code units, including surrogate pairs.
    value=0;data=text.encode('utf-16-be', errors='surrogatepass')
    for i in range(0,len(data),2): value=(31*value+int.from_bytes(data[i:i+2],'big'))&0xffffffff
    return value if value<0x80000000 else value-(1<<32)


@lru_cache(maxsize=1)
def library():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    path=root/'assets/native/onion_seedmap.dll'
    if not path.is_file(): raise RuntimeError('缺少种子地图组件，请运行 scripts/build_seedmap.py 后重新构建')
    dll=ctypes.CDLL(str(path))
    try:
        dll.onion_version.argtypes=[ctypes.c_char_p];dll.onion_version.restype=ctypes.c_int
        if not dll.onion_version(b'26.3'):raise AttributeError('Unsupported engine')
    except AttributeError:raise RuntimeError('种子地图组件版本过旧，请重新构建或更新启动器') from None
    dll.onion_biome_at.argtypes=[ctypes.c_char_p,ctypes.c_uint64,*([ctypes.c_int]*4)];dll.onion_biome_at.restype=ctypes.c_int
    dll.onion_map.argtypes=[ctypes.c_char_p,ctypes.c_uint64,*([ctypes.c_int]*7),ctypes.POINTER(ctypes.c_ubyte),ctypes.POINTER(ctypes.c_int)]
    dll.onion_map.restype=ctypes.c_int
    dll.onion_biome_name.argtypes=[ctypes.c_char_p,ctypes.c_int];dll.onion_biome_name.restype=ctypes.c_char_p
    dll.onion_structures.argtypes=[ctypes.c_char_p,ctypes.c_uint64,*([ctypes.c_int]*4),ctypes.POINTER(ctypes.c_int),ctypes.c_int]
    dll.onion_structures.restype=ctypes.c_int
    return dll


@dataclass
class MapData:
    rgb: bytes
    ids: list
    legend: dict
    structures: list
    origin: tuple
    scale: int
    size: int


def generate(seed, version, dimension=0, x=0, z=0, scale=16, y=64, size=256, structures=True):
    if version not in VERSIONS: raise ValueError('此版本尚未被地图引擎支持')
    if dimension not in (-1,0,1) or scale not in (1,4,16,64,256) or not 16<=size<=512:
        raise ValueError('无效的地图参数')
    if not all(isinstance(n,int) for n in (x,z,y,size)) or abs(x)>29_000_000 or abs(z)>29_000_000 or not -64<=y<=320:
        raise ValueError('坐标超过支持范围')
    seed=parse_seed(seed);dll=library();v=version.encode();count=size*size
    rgb=(ctypes.c_ubyte*(count*3))();ids=(ctypes.c_int*count)()
    ox=x//scale-size//2;oz=z//scale-size//2
    if dll.onion_map(v,seed,dimension,ox,oz,scale,size,size,y,rgb,ids): raise RuntimeError('地图生成失败')
    legend={}
    for biome in sorted(set(ids)):
        raw=dll.onion_biome_name(v,biome);legend[biome]=raw.decode() if raw else str(biome)
    markers=[]
    if structures:
        out=(ctypes.c_int*(512*3))()
        found=dll.onion_structures(v,seed,dimension,ox*scale,oz*scale,size*scale,out,512)
        if found<0: raise RuntimeError('结构定位失败')
        markers=[(STRUCTURES[out[3*i]],out[3*i+1],out[3*i+2]) for i in range(found)]
    return MapData(bytes(rgb),list(ids),legend,markers,(ox*scale,oz*scale),scale,size)


def structure_positions(seed,version,dimension,x,z,span):
    """Query a bounded square independently of biome tiles; filters stay client-side."""
    if version not in VERSIONS or dimension not in (-1,0,1):raise ValueError('无效的地图版本或维度')
    if not all(isinstance(n,int) for n in (x,z,span)) or not 1<=span<=32768 or max(abs(x),abs(z))>29_000_000:
        raise ValueError('结构查询超出范围')
    dll=library();out=(ctypes.c_int*(512*3))()
    found=dll.onion_structures(version.encode(),parse_seed(seed),dimension,x,z,span,out,512)
    if found<0:raise RuntimeError('结构定位失败')
    return [(STRUCTURES[out[3*i]],out[3*i+1],out[3*i+2]) for i in range(found)]
