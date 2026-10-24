"""Small Oklab palette/thumbnail scorer; stdlib + existing Qt, no runtime assets.

Oklab matrices: https://bottosson.github.io/posts/oklab/
Population/chroma scoring inspired by Material Color Utilities' documented
extraction pipeline. This is an independent bounded approximation, not HCT/MCU.
"""
import math
from functools import lru_cache


def linear(c):
    return c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4


def lab(rgb):
    r,g,b = map(linear,rgb)
    l=(.4122214708*r+.5363325363*g+.0514459929*b)**(1/3)
    m=(.2119034982*r+.6806995451*g+.1073969566*b)**(1/3)
    s=(.0883024619*r+.2817188376*g+.6299787005*b)**(1/3)
    return (.2104542553*l+.793617785*m-.0040720468*s,
            1.9779984951*l-2.428592205*m+.4505937099*s,
            .0259040371*l+.7827717662*m-.808675766*s)


def rgb_at(tone,chroma,hue):
    a,b=chroma*math.cos(hue),chroma*math.sin(hue)
    l=(tone+.3963377774*a+.2158037573*b)**3
    m=(tone-.1055613458*a-.0638541728*b)**3
    s=(tone-.0894841775*a-1.291485548*b)**3
    return (4.0767416621*l-3.3077115913*m+.2309699292*s,
            -1.2684380046*l+2.6097574011*m-.3413193965*s,
            -.0041960863*l-.7034186147*m+1.707614701*s)


def tone_color(tone,chroma,hue):
    # Reduce chroma at constant perceptual tone/hue until inside sRGB gamut.
    low,high=0.,max(0.,chroma)
    # Near the blue cusp, the valid chroma interval can be non-monotonic.
    # Preserve already in-gamut colors before applying conservative bisection.
    if all(-2e-7<=v<=1.0000002 for v in rgb_at(tone,high,hue)):low=high
    for _ in range(0 if low==high else 14):
        middle=(low+high)/2
        if all(-1e-7<=v<=1.0000001 for v in rgb_at(tone,middle,hue)):low=middle
        else:high=middle
    def encode(c):
        c=max(0.,min(1.,c));return round(255*(12.92*c if c<=.0031308 else 1.055*c**(1/2.4)-.055))
    return '#%02x%02x%02x'%tuple(map(encode,rgb_at(tone,low,hue)))


def channels(color):return tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
def luminance(color):return sum(c*w for c,w in zip(map(linear,channels(color)),(.2126,.7152,.0722)))
def contrast(a,b):
    lo,hi=sorted((luminance(a),luminance(b)));return (hi+.05)/(lo+.05)


def readable(color,background,minimum=4.5):
    if contrast(color,background)>=minimum:return color
    light,a,b=lab(channels(color));hue=math.atan2(b,a);chroma=math.hypot(a,b)
    target=0. if luminance(background)>.18 else 1.
    for step in range(1,65):
        candidate=tone_color(light+(target-light)*step/64,chroma,hue)
        if contrast(candidate,background)>=minimum:return candidate
    return '#000000' if target==0 else '#ffffff'


@lru_cache(maxsize=96)
def palette(seed,mode,style):
    light,a,b=lab(channels(seed));hue=math.atan2(b,a);chroma=math.hypot(a,b)
    chroma={'fidelity':max(.06,chroma),'tonal_spot':.09,'vibrant':.21,
            'neutral':.025,'fruit_salad':.15,'rainbow':.18}.get(style,.09)
    if style=='fruit_salad':hue-=math.pi/3
    if style=='rainbow':hue+=math.pi/3
    dark=mode=='dark';neutral=min(.025,chroma*.17)
    base=tone_color(.18 if dark else .975,neutral,hue)
    surface=tone_color(.235 if dark else .998,neutral,hue)
    accent=tone_color(.82 if dark else .46,chroma,hue)
    if style=='fidelity':accent=seed
    accent=readable(accent,base,3.)
    text=readable(tone_color(.94 if dark else .23,.015,hue),surface)
    muted=readable(tone_color(.73 if dark else .47,.025,hue),surface)
    return {'base':base,'surface':surface,'text':text,'muted':muted,'icon':muted,
            'selected_text':readable(accent,surface),'disabled':tone_color(.5 if dark else .65,.02,hue),
            'track':tone_color(.36 if dark else .82,neutral,hue),
            'thumb':text,'check':'#253047','hover':accent,'accent':accent,
            'container':tone_color(.32 if dark else .90,min(.07,chroma),hue)}


def image_seed(image,fallback='#cebafa'):
    """At most 4096 pixels / 512 RGB bins; no full-resolution pixel loops."""
    from PySide6.QtCore import Qt
    small=image.scaled(64,64,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    bins={}
    for y in range(small.height()):
        for x in range(small.width()):
            color=small.pixelColor(x,y)
            if color.alpha()<128:continue
            rgb=color.getRgb()[:3];key=tuple(c>>5 for c in rgb)
            n,r,g,b=bins.get(key,(0,0,0,0));bins[key]=(n+1,r+rgb[0],g+rgb[1],b+rgb[2])
    candidates=[]
    for n,r,g,b in bins.values():
        rgb=(r/n/255,g/n/255,b/n/255);light,a,b=lab(rgb);chroma=math.hypot(a,b)
        if .22<light<.92 and chroma>.035:
            candidates.append((n**.65*min(chroma,.22),rgb))
    if not candidates:return fallback
    _,rgb=max(candidates,key=lambda item:item[0])
    return '#%02x%02x%02x'%tuple(round(c*255) for c in rgb)


@lru_cache(maxsize=4)
def _wallpaper_seed(path,stamp):
    from PySide6.QtGui import QImageReader
    from PySide6.QtCore import QSize,Qt
    reader=QImageReader(path);size=reader.size()
    if not size.isValid() or size.width()*size.height()>64_000_000:return ''
    reader.setScaledSize(size.scaled(QSize(64,64),Qt.AspectRatioMode.KeepAspectRatio))
    image=reader.read()
    return image_seed(image,fallback='') if not image.isNull() else ''


def wallpaper_seed_info(path):
    from pathlib import Path
    try:seed=_wallpaper_seed(str(path),Path(path).stat().st_mtime_ns)
    except (OSError,ValueError):seed=''
    return seed or '#cebafa',bool(seed)


def wallpaper_seed(path):return wallpaper_seed_info(path)[0]
