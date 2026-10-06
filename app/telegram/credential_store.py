"""Store per-user Telegram API credentials in Windows Credential Manager."""

import ctypes
import os
from ctypes import wintypes

from app.constants import APP_NAME


SERVICE_NAME = f"{APP_NAME}.TelegramApi"
API_ID_KEY = "api_id"
API_HASH_KEY = "api_hash"
ERROR_NOT_FOUND = 1168
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class _CredentialW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _credential_api():
    if os.name != "nt":
        raise RuntimeError("Telegram credentials are supported on Windows only.")

    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CredentialW)),
    ]
    advapi.CredReadW.restype = wintypes.BOOL
    advapi.CredWriteW.argtypes = [ctypes.POINTER(_CredentialW), wintypes.DWORD]
    advapi.CredWriteW.restype = wintypes.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    advapi.CredFree.restype = None
    return advapi


def _read_secret(target_name):
    advapi = _credential_api()
    credential = ctypes.POINTER(_CredentialW)()
    if not advapi.CredReadW(
        target_name,
        CRED_TYPE_GENERIC,
        0,
        ctypes.byref(credential),
    ):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return None
        raise ctypes.WinError(error)

    try:
        entry = credential.contents
        blob = ctypes.string_at(
            entry.CredentialBlob,
            entry.CredentialBlobSize,
        )
        return blob.decode("utf-16-le")
    finally:
        advapi.CredFree(credential)


def _write_secret(target_name, value):
    advapi = _credential_api()
    blob = str(value).encode("utf-16-le")
    buffer = ctypes.create_string_buffer(blob)
    credential = _CredentialW(
        Flags=0,
        Type=CRED_TYPE_GENERIC,
        TargetName=target_name,
        Comment=f"{APP_NAME} Telegram API credential",
        LastWritten=wintypes.FILETIME(0, 0),
        CredentialBlobSize=len(blob),
        CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        Persist=CRED_PERSIST_LOCAL_MACHINE,
        AttributeCount=0,
        Attributes=None,
        TargetAlias=None,
        UserName=APP_NAME,
    )
    if not advapi.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def get_credentials():
    api_id = _read_secret(f"{SERVICE_NAME}/{API_ID_KEY}")
    api_hash = _read_secret(f"{SERVICE_NAME}/{API_HASH_KEY}")
    if not api_id or not api_hash:
        return None
    return api_id, api_hash


def save_credentials(api_id, api_hash):
    _write_secret(f"{SERVICE_NAME}/{API_ID_KEY}", api_id)
    _write_secret(f"{SERVICE_NAME}/{API_HASH_KEY}", api_hash)
