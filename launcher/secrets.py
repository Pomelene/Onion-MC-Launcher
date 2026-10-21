"""User-bound Windows DPAPI storage. Never falls back to plaintext."""
import base64
import ctypes
import json
import os
from ctypes import wintypes


class SecretStorageError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(value, decrypt=False):
    if os.name!='nt':
        raise SecretStorageError('当前系统没有配置安全凭据存储，已拒绝明文保存令牌')
    buffer=ctypes.create_string_buffer(value)
    source=_Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    output=_Blob()
    crypt32=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    function=crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes=[ctypes.POINTER(_Blob),ctypes.c_void_p,ctypes.POINTER(_Blob),
                       ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Blob)]
    function.restype=wintypes.BOOL
    kernel32.LocalFree.argtypes=[ctypes.c_void_p];kernel32.LocalFree.restype=ctypes.c_void_p
    # No machine-wide key and no UI prompts: binds the blob to the current user.
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise SecretStorageError('无法访问当前 Windows 用户的安全凭据存储，请重新登录账号')
    try:return ctypes.string_at(output.data,output.size)
    finally:kernel32.LocalFree(output.data)


def protect(values):
    raw=json.dumps(values,separators=(',',':')).encode('utf-8')
    return {'scheme':'windows-dpapi-v1','data':base64.b64encode(_crypt(raw)).decode('ascii')}


def unprotect(envelope):
    try:
        if envelope.get('scheme')!='windows-dpapi-v1':raise ValueError()
        data=json.loads(_crypt(base64.b64decode(envelope['data'],validate=True),True))
        if not isinstance(data,dict) or not all(isinstance(v,str) for v in data.values()):raise ValueError()
        return data
    except (ValueError,KeyError,TypeError,AttributeError,UnicodeError):
        raise SecretStorageError('凭据数据无效，请重新登录账号') from None
