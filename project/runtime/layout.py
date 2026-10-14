"""Resolve a new or immutable historical packet; never rewrite it."""
from inference.reuse import safe_file

def packet_runtime_file(packet, name):
    for prefix in ('project/runtime/', 'project/next/runtime/'):
        if (packet / prefix / name).is_file():
            return safe_file(packet, prefix + name)
    raise FileNotFoundError('FROZEN_RUNTIME_FILE_MISSING')
