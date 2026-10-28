"""Desktop OAuth, fixed Google endpoints, and OS-protected local token storage."""
import ctypes
import json
import os
import sys
import threading
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']


def protect(data: bytes, decrypt=False) -> bytes:
    if sys.platform != 'win32':
        return data
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.restype = wintypes.BOOL
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError(ctypes.get_last_error(), 'Windows could not access the protected credentials.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


class Auth:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.RLock()

    def read(self, name):
        path = self.root / (name + '.vault')
        if not path.exists():
            return None
        return json.loads(protect(path.read_bytes(), decrypt=True))

    def write(self, name, value):
        path = self.root / (name + '.vault')
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(protect(json.dumps(value).encode('utf-8')))
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def configure(self, config):
        installed = config.get('installed', {})
        if not installed.get('client_id', '').endswith('.apps.googleusercontent.com') or not installed.get('client_secret'):
            raise ValueError('Choose the JSON credentials for a Google OAuth Desktop app.')
        if installed.get('auth_uri') not in {'https://accounts.google.com/o/oauth2/auth', 'https://accounts.google.com/o/oauth2/v2/auth'}:
            raise ValueError('The authorization endpoint must be Google Accounts.')
        if installed.get('token_uri') != 'https://oauth2.googleapis.com/token':
            raise ValueError('The token endpoint must be Google OAuth.')
        self.write('client', {'installed': installed})
        self.forget_token()

    def forget_token(self):
        (self.root / 'token.vault').unlink(missing_ok=True)

    def configured(self):
        return (self.root / 'client.vault').exists()

    def connected(self):
        return (self.root / 'token.vault').exists()

    def login(self):
        with self.lock:
            config = self.read('client')
            if not config:
                raise ValueError('Import Google OAuth Desktop app credentials first.')
            flow = InstalledAppFlow.from_client_config(config, SCOPES, autogenerate_code_verifier=True)
            creds = flow.run_local_server(host='127.0.0.1', port=0, open_browser=True, timeout_seconds=120,
                authorization_prompt_message='', success_message='Connected. You may close this tab and return to YouTube Spam Cleaner.',
                access_type='offline', prompt='consent')
            self.write('token', json.loads(creds.to_json()))
            return creds

    def credentials(self):
        with self.lock:
            data = self.read('token')
            if not data:
                raise ValueError('Connect your YouTube channel in Settings first.')
            creds = Credentials.from_authorized_user_info(data, SCOPES)
            if not creds.valid:
                if not creds.refresh_token:
                    raise ValueError('Your session expired. Connect your channel again.')
                try:
                    creds.refresh(Request())
                except Exception as exc:
                    raise ValueError('Google could not refresh your session. Connect your channel again.') from exc
                self.write('token', json.loads(creds.to_json()))
            return creds
