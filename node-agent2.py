#!/usr/bin/env python3
# This node agent is used to test p2p connection
import os
import json
import re
import threading
import time
from lib.fetch import fetch
from lib.server import listen
from lib.cancellable import Cancellable
from lib.regexp import RegExpBuffer

NODE_ADDRESS = ("127.0.0.1", 7092)  # Note: change later
TRACKER_ADDRESS = ("127.0.0.1", 7090)

re_peer_connect = re.compile(r"^peer_connect:(.+)$")
re_chat = re.compile(r"^chat:(.+)$")
re_file_transfer = re.compile(r"^file_transfer:(.+)$")
re_result = re.compile(r"^result:(.+)$")

PEERS = {}
PENDING_CONNECTIONS = {}
TRACKER_INFO = {}

cancellable = Cancellable()
cancellable.set()

# Set up shmem communication files
app_path = os.path.dirname(os.path.abspath(__file__))
nodes_dir = os.path.join(app_path, "_nodes")
os.makedirs(nodes_dir, exist_ok=True)

node_address_str = f"{NODE_ADDRESS[0]}:{NODE_ADDRESS[1]}"
in_file = os.path.join(nodes_dir, f"{node_address_str}.in")
out_file = os.path.join(nodes_dir, f"{node_address_str}.out")

# Create empty files if they don't exist
open(in_file, 'a').close()
open(out_file, 'a').close()

def write_response(response):
    with open(out_file, 'a') as f:
        f.write(response + "\n")

def peer_connect(address):
    def on_response(response):
        regexp = RegExpBuffer()
        if regexp.match(re_result, response):
            body = regexp.group(1)
            result = json.loads(body)
            if result["status"] == "OK":
                PEERS[address] = result["token"]
                print(f"agent: Successfully connected to peer {address}")
                write_response(f"Connected to peer {address}")
            else:
                print(f"agent: Failed to connect to peer {address}: {result['message']}")
                write_response(f"Failed to connect to peer {address}: {result['message']}")
        else:
            print(f"agent: Invalid response from peer: {response}")
            write_response(f"Invalid response from peer {address}")
    
    if isinstance(address, str) and ":" in address:
        host, port = address.split(":")
        port = int(port)
    else:
        host, port = address
    
    peer_address = (host, port)
    body = {"address": NODE_ADDRESS}
    
    print(f"agent: Connecting to peer at {peer_address}")
    fetch(peer_address, "peer_connect", body, on_response)

def submit_info():
    """Submit node information to the tracker"""
    def on_response(response):
        print(f"agent: tracker responded: \"{response}\"")
        try:
            data = json.loads(response)
            global TRACKER_INFO
            TRACKER_INFO = data
            write_response(f"Tracker update: {len(data)} nodes online")
        except json.JSONDecodeError:
            print(f"agent: Invalid JSON response from tracker")
            write_response("Invalid response from tracker")
    
    body = {"address": NODE_ADDRESS}
    print(f"agent: submitting info to tracker")
    fetch(TRACKER_ADDRESS, "submit_info", body, on_response)

def get_list():
    """Get the list of nodes from the tracker"""
    def on_response(response):
        print(f"agent: tracker responded with list: \"{response}\"")
        try:
            data = json.loads(response)
            global TRACKER_INFO
            TRACKER_INFO = data
            write_response(f"Tracker list: {data}")
        except json.JSONDecodeError:
            print(f"agent: Invalid JSON response from tracker")
            write_response("Invalid response from tracker")
    
    print(f"agent: requesting node list from tracker")
    fetch(TRACKER_ADDRESS, "get_list", {}, on_response)

def send_chat_message(peer, message):
    """Send a chat message to a peer"""
    if peer not in PEERS:
        print(f"agent: Peer {peer} not connected")
        write_response(f"Error: Peer {peer} not connected")
        return
    
    def on_response(response):
        print(f"agent: peer {peer} responded to chat: \"{response}\"")
        write_response(f"Message sent to {peer}")
    
    if isinstance(peer, str) and ":" in peer:
        host, port = peer.split(":")
        port = int(port)
    else:
        host, port = peer
    
    peer_address = (host, port)
    body = {
        "token": PEERS[peer],
        "message": message,
        "from": node_address_str
    }
    
    print(f"agent: Sending chat message to {peer}: {message}")
    fetch(peer_address, "chat_message", body, on_response)

def send_file(peer, file_data):
    """Send a file to a peer"""
    if peer not in PEERS:
        print(f"agent: Peer {peer} not connected")
        write_response(f"Error: Peer {peer} not connected")
        return
    
    def on_response(response):
        print(f"agent: peer {peer} responded to file transfer: \"{response}\"")
        write_response(f"File sent to {peer}")
    
    if isinstance(peer, str) and ":" in peer:
        host, port = peer.split(":")
        port = int(port)
    else:
        host, port = peer
    
    peer_address = (host, port)
    body = {
        "token": PEERS[peer],
        "file": file_data,
        "from": node_address_str
    }
    
    print(f"agent: Sending file to {peer}: {file_data.get('filename', 'unknown')}")
    fetch(peer_address, "file_transfer", body, on_response)

def handle_connection(request, response):
    """Handle incoming connections from peers"""
    message = request.message
    regexp = RegExpBuffer()
    
    if regexp.match(re_peer_connect, message):
        body = regexp.group(1)
        try:
            data = json.loads(body)
            peer_address = data["address"]
            
            token = f"token_{int(time.time())}"
            peer_address_str = f"{peer_address[0]}:{peer_address[1]}"
            PEERS[peer_address_str] = token
            
            result = {
                "status": "OK",
                "token": token
            }
            
            print(f"agent: Peer {peer_address_str} connected")
            write_response(f"Peer {peer_address_str} connected")
            response.write(f"result:{json.dumps(result)}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"agent: Invalid peer_connect request: {e}")
            result = {
                "status": "ERROR",
                "message": f"Invalid request: {str(e)}"
            }
            response.write(f"result:{json.dumps(result)}")
    
    elif regexp.match(re_chat, message):
        body = regexp.group(1)
        try:
            data = json.loads(body)
            message_text = data["message"]
            from_peer = data.get("from", "unknown")
            token = data.get("token")
            
            if from_peer in PEERS and PEERS[from_peer] == token:
                print(f"agent: Chat message from {from_peer}: {message_text}")
                write_response(f"CHAT:{from_peer}:{message_text}")
                
                result = {
                    "status": "OK",
                    "message": "Message received"
                }
                response.write(f"result:{json.dumps(result)}")
            else:
                print(f"agent: Unauthorized chat message from {from_peer}")
                result = {
                    "status": "ERROR",
                    "message": "Unauthorized"
                }
                response.write(f"result:{json.dumps(result)}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"agent: Invalid chat request: {e}")
            result = {
                "status": "ERROR",
                "message": f"Invalid request: {str(e)}"
            }
            response.write(f"result:{json.dumps(result)}")
    
    elif regexp.match(re_file_transfer, message):
        body = regexp.group(1)
        try:
            data = json.loads(body)
            file_data = data.get("file", {})
            from_peer = data.get("from", "unknown")
            token = data.get("token")
            
            if from_peer in PEERS and PEERS[from_peer] == token:
                filename = file_data.get("filename", "unknown")
                print(f"agent: File received from {from_peer}: {filename}")
                write_response(f"FILE:{from_peer}:{json.dumps(file_data)}")
                
                result = {
                    "status": "OK",
                    "message": "File received"
                }
                response.write(f"result:{json.dumps(result)}")
            else:
                print(f"agent: Unauthorized file transfer from {from_peer}")
                result = {
                    "status": "ERROR",
                    "message": "Unauthorized"
                }
                response.write(f"result:{json.dumps(result)}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"agent: Invalid file transfer request: {e}")
            result = {
                "status": "ERROR",
                "message": f"Invalid request: {str(e)}"
            }
            response.write(f"result:{json.dumps(result)}")
    
    else:
        print(f"agent: Unknown request: {message}")
        result = {
            "status": "ERROR",
            "message": "Unknown request"
        }
        response.write(f"result:{json.dumps(result)}")

def process_commands():
    """Process commands from the shared memory input file"""
    while cancellable.is_set():
        try:
            with open(in_file, 'r') as f:
                content = f.read().strip()
            
            if content:
                with open(in_file, 'w') as f:
                    pass
                
                print(f"agent: Received command: {content}")
                
                if content == "exit":
                    print("agent: Exiting...")
                    cancellable.clear()
                    break
                elif content == "submit_info":
                    submit_info()
                elif content == "get_list":
                    get_list()
                elif content.startswith("peer_connect:"):
                    try:
                        address = content[len("peer_connect:"):]
                        try:
                            address_data = json.loads(address)
                            address = address_data
                        except json.JSONDecodeError:
                            pass
                        peer_connect(address)
                    except Exception as e:
                        print(f"agent: Error in peer_connect: {e}")
                        write_response(f"Error in peer_connect: {e}")
                elif content.startswith("chat:"):
                    try:
                        data = json.loads(content[len("chat:"):])
                        peer = data["peer"]
                        message = data["message"]
                        send_chat_message(peer, message)
                    except Exception as e:
                        print(f"agent: Error in chat: {e}")
                        write_response(f"Error in chat: {e}")
                elif content.startswith("file:"):
                    try:
                        data = json.loads(content[len("file:"):])
                        peer = data["peer"]
                        file_data = data["file"]
                        send_file(peer, file_data)
                    except Exception as e:
                        print(f"agent: Error in file transfer: {e}")
                        write_response(f"Error in file transfer: {e}")
                else:
                    print(f"agent: Unknown command: {content}")
                    write_response(f"Unknown command: {content}")
            
            time.sleep(0.5)  
        except Exception as e:
            print(f"agent: Error processing command: {e}")
            time.sleep(1)  

if __name__ == "__main__":
    print(f"Node agent starting with address {node_address_str}")
    write_response(f"Node agent started with address {node_address_str}")
    
    command_thread = threading.Thread(target=process_commands)
    command_thread.daemon = True
    command_thread.start()
    
    server_thread = threading.Thread(target=listen, args=(NODE_ADDRESS, handle_connection, cancellable))
    server_thread.daemon = True
    server_thread.start()
    
    submit_info()
    
    try:
        while cancellable.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("agent: Interrupted, shutting down...")
        cancellable.clear()