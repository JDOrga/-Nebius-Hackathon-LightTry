"""Windows CPU provider: WSL runs ONLY CLI; all durable session DB writes stay native."""
import os
from pathlib import PurePosixPath
import re

from nebius_provider import NebiusProvider


def build(binding):return WSLNebiusProvider(binding)


class WSLNebiusProvider(NebiusProvider):
    def __init__(self,binding):
        extra={'wslDistro','linuxCliPath','linuxConfigFile'}
        required={'cliPath','configFile','profile','tenantId','projectId','resourceId','publicKeyFile','guardRoot'}
        if not isinstance(binding,dict) or set(binding)!=required|extra:raise ValueError('EXPLICIT_WSL_NEBIUS_BINDING_REQUIRED')
        if os.name!='nt':raise ValueError('WINDOWS_WSL_PROVIDER_REQUIRED')
        distro=binding['wslDistro']
        if not isinstance(distro,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,64}',distro):raise ValueError('WSL_DISTRO_INVALID')
        for field in ('linuxCliPath','linuxConfigFile'):
            path=binding[field]
            if not isinstance(path,str) or not PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
                raise ValueError('ABSOLUTE_WSL_RUNTIME_PATH_REQUIRED')
        expected='\\\\wsl.localhost\\'+distro+binding['linuxConfigFile'].replace('/','\\')
        if binding['configFile']!=expected:raise ValueError('WSL_AUTH_CONFIG_IDENTITY_MISMATCH')
        self.wsl={key:binding[key] for key in extra}
        # Checks only explicit native executable/key/config files; no CLI or API.
        super().__init__({key:binding[key] for key in required})
        if self.cli.name.lower()!='wsl.exe':raise ValueError('EXPLICIT_WSL_EXECUTABLE_REQUIRED')

    def _command(self,args,json_result):
        command=super()._command(args,json_result)
        command[command.index('--config')+1]=self.wsl['linuxConfigFile']
        return [str(self.cli),'-d',self.wsl['wslDistro'],'--',self.wsl['linuxCliPath'],*command[1:]]
