import argparse
import json
import subprocess
import sys
import traceback
import time
import uuid
import select
import random
from datetime import datetime, timedelta, timezone
import os  # Import the os module
import sqlite3
from typing import List, Tuple

from typing import Dict, List, Tuple  # Import Dict and Tuple from typing

def get_pod_mapping(topology_folder: str, filename: str) -> Dict[str, Tuple[str, int]]:
    """
    Returns:
        {
            "gossip-0": ("10.1.0.1", 0),
            "gossip-1": ("10.1.0.2", 1),
            ...
        }
    """
    # 1. Load topology JSON
    topology_file_path = os.path.join(os.getcwd(), topology_folder, filename)

    if not os.path.exists(topology_file_path):
        print(f"Error: Topology file not found at '{topology_file_path}'. Exiting.", flush=True)
        sys.exit(1)

    try:
        with open(topology_file_path) as f:
            topology = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from file '{topology_file_path}'. Exiting.", flush=True)
        sys.exit(1)

    # 2. Get live pod IPs from Kubernetes
    live_pods_list = get_live_pods_as_list()
    print(f"live_pods_list ={live_pods_list}")

    # 3. Create mapping with direct index matching
    pod_map = {}
    for idx, node in enumerate(topology['nodes']):
        pod_name_from_topology = node['id']
        if idx < len(live_pods_list):
            pod_name_live, pod_ip = live_pods_list[idx]
            pod_map[pod_name_from_topology] = (pod_ip, pod_name_live)
        else:
            pod_map[pod_name_from_topology] = ("UNASSIGNED", f"unassigned-{idx}")

    print(f"pod_map ={pod_map}")
    return pod_map

def get_live_pods_as_list() -> List[Tuple[str, str]]:
    """Fetches [(pod_name, pod_ip)] from Kubernetes as a list, sorted by name."""
    cmd = [
        'kubectl',
        'get', 'pods',
        '-l', 'app=bcgossip',
        '-o', 'jsonpath={range .items[*]}{.metadata.name}{" "}{.status.podIP}{"\\n"}{end}'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    pods_data = [line.split() for line in result.stdout.splitlines() if line]
    # Sort the pods by name to attempt a consistent ordering
    pods_data.sort(key=lambda x: x[0])
    return pods_data

def get_neighbor_info(pod_mapping: Dict[str, Tuple[str, int]], topology: Dict) -> Dict[str, List[Tuple[str, str]]]:
    """
    Gets the neighbor pod names and IP addresses for each pod based on the topology.

    Args:
        pod_mapping: A dictionary mapping topology node names to (IP address, live pod name).
        topology: The loaded topology JSON data.

    Returns:
        A dictionary where the key is the pod name and the value is a list of
        tuples, with each tuple containing the neighbor's pod name and IP address.
    """
    neighbor_info = {}
    for node in topology['nodes']:
        node_name_topology = node['id']
        # Getting live pod name
        for pod_topology_name, pod_live in pod_mapping.items():
            if node_name_topology == pod_topology_name:
                print(f"pod_live={pod_live},pod_live[0]={pod_live[0]},,pod_live[1]={pod_live[1]}")

        neighbor_info[node_name_topology] = []
        for edge in topology['edges']:
            neighbor_name = None
            if edge['source'] == node_name_topology:
                neighbor_name = edge['target']
            elif edge['target'] == node_name_topology:
                neighbor_name = edge['source']

            if neighbor_name and neighbor_name != node_name_topology:
                neighbor_ip, neighbor_live_name = pod_mapping.get(neighbor_name, ("UNASSIGNED", f"unassigned-{neighbor_name}"))
                # neighbor_info[node_name_topology].append((neighbor_live_name, neighbor_ip))
                neighbor_info[node_name_topology].append(neighbor_ip)
    return neighbor_info

def update_pod_neighbors(pod: str, neighbors_tuple) -> bool:
    """
    Atomically updates neighbor list in a pod's SQLite DB.

    Args:
        pod: Pod name (e.g. 'gossip-0')
        neighbors: List of (pod_name, ip) tuples

    Returns:
        bool: True if successful, False if failed
    """
    # 1. Prepare SQLite commands with proper escaping
    # neighbors_json = json.dumps([ip for (_, ip) in neighbors])
    python_script = f"""
    import sqlite3

    try:
        values = '{neighbors_tuple}'
        with sqlite3.connect('ned.db') as conn:
            conn.execute('BEGIN TRANSACTION')
            conn.execute('DROP TABLE IF EXISTS NEIGHBORS')
            conn.execute('''CREATE TABLE NEIGHBORS (
                pod_ip TEXT PRIMARY KEY,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.executemany('INSERT INTO NEIGHBORS (pod_ip) VALUES (?)', values)
            conn.commit()
            print(f"Updated {{len(values)}} neighbors")
    except Exception as e:
        print(f"Error: {{str(e)}}")
        raise
    """

    # 2. Execute via kubectl
    cmd = [
        'kubectl', 'exec', pod,
        '--', 'python3', '-c', python_script
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            text=True,
            capture_output=True,
            timeout=30  # Fail if stuck
        )
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to update {pod}: {e.stderr}")
        return False

# Example Usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get pod mapping and neighbor info based on topology.")
    parser.add_argument("--filename", help="Name of the topology JSON file in the 'topology' folder.")
    parser.add_argument("--topology_folder", default="topology", help="Name of the topology folder from the root.")
    args = parser.parse_args()

    pod_mapping = get_pod_mapping(args.topology_folder, args.filename)

    if pod_mapping:
        print("Pod Name\tIP Address\tLive Pod Name")
        print("-" * 40)
        for name, (ip, live_name) in pod_mapping.items():
            print(f"{name}\t{ip}\t{live_name}")

        topology_file_path = os.path.join(os.getcwd(), args.topology_folder, args.filename)
        try:
            with open(topology_file_path) as f:
                topology_data = json.load(f)
                neighbor_data = get_neighbor_info(pod_mapping, topology_data)
                print("\nNeighbor Information:")
                print(f"neighbor_data : {neighbor_data} \n")
                print(f"topology_data : {topology_data} \n")
                for pod, neighbors in neighbor_data.items():
                    neighbors_tuple = [(ip_addr,) for ip_addr in neighbors]
                    print(f"Neighbors of {pod}: {neighbors_tuple}")
                    if update_pod_neighbors(pod, neighbors_tuple):
                        print(f"Pod:{pod} neighbors Updated")
                    else:
                        print(f"Pod:{pod} neighbors Not Updated")
        except FileNotFoundError:
            print(f"Error: Topology file not found at '{topology_file_path}'.")
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from file '{topology_file_path}'.")

    else:
        print("Pod mapping could not be generated due to errors.")


# Connecting to sqlite
conn = sqlite3.connect('neighbors.db')
cursor = conn.cursor()  # Add cursor

print("Opened database successfully")
cursor.execute('''CREATE TABLE IF NOT EXISTS NEIGHBORS ( 
         pod_ip VARCHAR(25) NOT NULL UNIQUE
         );''')
print("Table created / existed successfully")

# Sample data
values = [('10.52.1.27',), ('10.52.0.26',), ('10.52.1.26',), ('10.52.5.23',), ('10.52.6.18',)] # Correct data format
cursor.executemany("""
    INSERT OR REPLACE INTO NEIGHBORS (pod_ip)
    VALUES (?)
    """, values)
conn.commit()  # Add commit


cursor = conn.execute("SELECT pod_ip from NEIGHBORS")
susceptible_nodes = []
for row in cursor:
   susceptible_nodes.append(row[0])
print(f"susceptible_nodes: {susceptible_nodes}")
conn.close()

