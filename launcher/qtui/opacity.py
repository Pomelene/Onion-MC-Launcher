"""One explicit opacity model for Qt stylesheets and byte-alpha painters.

Ratios are always 0..1; byte alpha is only quantized at the paint boundary.
QSS receives native #AARRGGBB byte colors: integer rgba alpha 1 means opaque.
"""
import math

def opacity(transparency,maximum=100):
    try:value=float(transparency)
    except (ValueError,TypeError):value=0.
    if not math.isfinite(value):value=0.
    return 1-max(0.,min(float(maximum),value))/100

def alpha_byte(ratio):return round(255*max(0.,min(1.,ratio)))

def qss_color(rgb,ratio):
    # Native Qt ARGB is exact at both 0x00/0x01 and 0xfe/0xff boundaries.
    # It avoids the integer-1 ambiguity and floating-point alpha truncation.
    return '#%02x%02x%02x%02x'%(alpha_byte(ratio),*rgb)

def parse_source_color(value):
    """Parse our authored #RRGGBB / rgba(r,g,b,byte-alpha) tokens, never QSS output."""
    if value.startswith('#'):
        if len(value)==9:return tuple(int(value[i:i+2],16) for i in (3,5,7)),int(value[1:3],16)/255
        return tuple(int(value[i:i+2],16) for i in (1,3,5)),1.
    parts=value[value.index('(')+1:-1].split(',')
    rgb=tuple(int(v) for v in parts[:3]);alpha=parts[3].strip()
    return rgb,float(alpha) if '.' in alpha else int(alpha)/255
