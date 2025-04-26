#!/usr/bin/env python3
import re
import json
import socket
import threading
import time
from lib.cancellable import Cancellable
from lib.server import listen
from lib.regexp import RegExpBuffer

re_submit_info = re.compile(r"^submit_info:(.+)$")
re_get_list = re.compile(r"^get_list:?(.*)$")
re_get_ip = re.compile(r"^get_ip$")

ADDRESS = ("0.0.0.0", 7090) 

TRACKING = {} 

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"  # Fallback to localhost
    finally:
        s.close()
    return ip

def add_node(body):
    global TRACKING
    node_key = f"{body['address'][0]}:{body['address'][1]}"
    TRACKING[node_key] = {
        "last_seen": time.time(),
        "status": "online"
    }
    return node_key

def get_list(client_ip=None):
    current_time = time.time()
    active_nodes = {k: v for k, v in TRACKING.items() 
                   if current_time - v["last_seen"] < 300}
    
    TRACKING.clear()
    TRACKING.update(active_nodes)
    
    return json.dumps(TRACKING)

def on_connection(request, response):
    print(f"tracker: received from client: \"{request.message}\"")
    client_ip = request.address[0]
    regexp = RegExpBuffer()
    
    if regexp.match(re_submit_info, request.message):
        print(f"tracker: request is submit_info from {client_ip}")
        body = regexp.group(1)
        body = json.loads(body)
        node_key = add_node(body)
        print(f"tracker: added node {node_key}")
        response.write(get_list(client_ip))
    
    elif regexp.match(re_get_list, request.message):
        print(f"tracker: request is get_list from {client_ip}")
        response.write(get_list(client_ip))
    
    elif regexp.match(re_get_ip, request.message):
        print(f"tracker: request is get_ip from {client_ip}")
        response.write(json.dumps({"ip": client_ip}))
    
    else:
        print(f"tracker: unknown request {request.message}")
        response.write(json.dumps({"error": "Unknown request"}))

def cleanup_thread():
    while True:
        time.sleep(60) 
        current_time = time.time()
        inactive = []
        
        for node, data in TRACKING.items():
            if current_time - data["last_seen"] > 300: 
                inactive.append(node)
        
        for node in inactive:
            del TRACKING[node]
            print(f"tracker: removed inactive node {node}")

if __name__ == "__main__":
    print("Starting tracker service on", ADDRESS)
    
    cleanup = threading.Thread(target=cleanup_thread)
    cleanup.daemon = True
    cleanup.start()
    
    cancellable = Cancellable()
    cancellable.set()
    try:
        listen(ADDRESS, on_connection, cancellable)
    except KeyboardInterrupt:
        print("Tracker shutting down...")
        cancellable.clear()