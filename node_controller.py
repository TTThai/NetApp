#!/usr/bin/env python3
import os
import json
import time
from pathlib import Path

class NodeController:
    def __init__(self, app_path=None):
        if app_path is None:
            # Default to current directory
            self.app_path = os.path.dirname(os.path.abspath(__file__))
        else:
            self.app_path = app_path
        
        # Create _nodes directory if it doesn't exist
        self.nodes_dir = os.path.join(self.app_path, "_nodes")
        os.makedirs(self.nodes_dir, exist_ok=True)
    
    def send_command(self, node_address, command, data=None):
        """
        Send a command to a node through shared memory
        node_address: is IP in inet6
        """
        in_file = os.path.join(self.nodes_dir, f"{node_address}.in")
        
        if data:
            message = f"{command}:{json.dumps(data)}"
        else:
            message = command
        
        with open(in_file, 'w') as f:
            f.write(message)
        
        return True
    
    def get_response(self, node_address):
        out_file = os.path.join(self.nodes_dir, f"{node_address}.out")
        
        if not os.path.exists(out_file):
            return None
        
        with open(out_file, 'r') as f:
            content = f.read()
        
        with open(out_file, 'w') as f:
            pass
        
        return content
    
    def peer_connect(self, node_address, peer_address):
        return self.send_command(node_address, "peer_connect", peer_address)
    
    def submit_info(self, node_address):
        return self.send_command(node_address, "submit_info")
    
    def exit_node(self, node_address):
        return self.send_command(node_address, "exit")
    
    def send_chat(self, node_address, peer_address, message):
        data = {
            "peer": peer_address,
            "message": message
        }
        return self.send_command(node_address, "chat", data)

if __name__ == "__main__":
    controller = NodeController()
    node_address = "127.0.0.1:8000"
    
    controller.peer_connect(node_address, "127.0.0.1:8001")
    
    controller.submit_info(node_address)
    
    time.sleep(1)
    response = controller.get_response(node_address)
    print(f"Response: {response}")