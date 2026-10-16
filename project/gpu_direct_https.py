"""Render inactive IP-independent mTLS ingress. No network/process side effects."""
import ipaddress,re

def render(cpu_cidr,container_ip,*,listen_port=443,worker_port=9443,
           server_certificate='/etc/lighttry/server.crt',server_key='/etc/lighttry/server.key',
           client_ca='/etc/lighttry/cpu-ca.crt',worker_ca='/etc/lighttry/worker-ca.crt'):
    # Legacy positional slot kept for callers; never used as an access control.
    if cpu_cidr is not None:raise ValueError('FIXED_SOURCE_IP_NOT_SUPPORTED_USE_MTLS')
    target=ipaddress.ip_address(container_ip)
    if target.version!=4 or not any(target in ipaddress.ip_network(n) for n in ['127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']):raise ValueError('PRIVATE_CONTAINER_IPV4_REQUIRED')
    if any(type(p) is not int or not 1<=p<=65535 for p in [listen_port,worker_port]):raise ValueError('PORT_INVALID')
    for p in [server_certificate,server_key,client_ca,worker_ca]:
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+',p) or '..' in p.split('/'):raise ValueError('SAFE_ABSOLUTE_TLS_PATH_REQUIRED')
    return f'''# Nginx stream+stream_ssl modules required; NOT installed by renderer.
# Dedicated current-session client CA. No source IP whitelist.
stream {{
    limit_conn_zone $binary_remote_addr zone=per_source:1m;
    server {{
        listen {listen_port} ssl;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_certificate {server_certificate};
        ssl_certificate_key {server_key};
        ssl_client_certificate {client_ca};
        ssl_verify_client on;
        ssl_verify_depth 1;
        ssl_handshake_timeout 5s;
        ssl_session_cache off;
        ssl_session_tickets off;
        limit_conn per_source 4;
        proxy_connect_timeout 3s;
        proxy_timeout 15s;
        proxy_ssl on;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate {worker_ca};
        proxy_ssl_name localhost;
        proxy_ssl_server_name on;
        proxy_pass {target}:{worker_port};
    }}
}}
'''
