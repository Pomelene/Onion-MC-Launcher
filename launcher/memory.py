"""Conservative Java heap sizing, independent of UI and game data."""
import ctypes
import os


def physical_memory_mb():
    if os.name == 'nt':
        class MemoryStatus(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        status=MemoryStatus();status.length=ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total//1024**2
    try:return os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')//1024**2
    except (AttributeError,OSError,ValueError):return 8192


def recommended_memory(total_mb=None):
    total=physical_memory_mb() if total_mb is None else max(0,int(total_mb))
    maximum=max(512,min(8192,(total//2//256)*256))
    return min(1024,maximum),maximum
