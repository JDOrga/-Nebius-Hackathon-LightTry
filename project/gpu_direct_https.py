"""Render an inactive, source-restricted raw TLS relay; no process/network actions."""
import ipaddress

def render(cpu_cidr,container_ip,*,listen_port=443,worker_port=9443):
    cpu=ipaddress.ip_network(cpu_cidr,strict=True);target=ipaddress.ip_address(container_ip)
    if cpu.version!=4 or cpu.prefixlen!=32:raise ValueError('EXACT_CPU_EGRESS_IPV4_REQUIRED')
    if target.version!=4 or not any(target in ipaddress.ip_network(n) for n in ['127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']):raise ValueError('PRIVATE_CONTAINER_IPV4_REQUIRED')
    if any(type(p) is not int or not 1<=p<=65535 for p in [listen_port,worker_port]):raise ValueError('PORT_INVALID')
    return f'''# Nginx stream module required. Raw TLS passthrough; no TLS termination or credentials here.
# Install only after current VM identity, container address and CPU source are verified.
stream {{
    server {{
        listen {listen_port};
        allow {cpu};
        deny all;
        proxy_connect_timeout 3s;
        proxy_timeout 15s;
        proxy_pass {target}:{worker_port};
    }}
}}
'''
