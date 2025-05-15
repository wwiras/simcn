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
    # for idx, node in enumerate(topology['nodes']):
    #     pod_name_from_topology = node['id']
    #     if idx < len(live_pods_list):
    #         pod_name_live, pod_ip = live_pods_list[idx]
    #         pod_map[pod_name_from_topology] = (pod_ip, idx)
    #     else:
    #         pod_map[pod_name_from_topology] = ("UNASSIGNED", idx)

    for idx, node in enumerate(topology['nodes']):
        pod_name_from_topology = node['id']
        if idx < len(live_pods_list):
            pod_name_live, pod_ip = live_pods_list[idx]
            pod_map[pod_name_from_topology] = (pod_ip, pod_name_live)
        else:
            pod_map[pod_name_from_topology] = ("UNASSIGNED", pod_name_live)

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


# Example Usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get pod mapping based on topology.")
    parser.add_argument("--filename", help="Name of the topology JSON file in the 'topology' folder.")
    parser.add_argument("--topology_folder", default="topology", help="Name of the topology folder from the root.")
    args = parser.parse_args()

    pod_mapping = get_pod_mapping(args.topology_folder, args.filename)

    if pod_mapping:
        print("Pod Name\tIP Address\tJSON Index")
        print("-" * 40)
        for name, (ip, idx) in pod_mapping.items():
            print(f"{name}\t{ip}\t{idx}")

        # Access specific pod
        if 'gossip-0' in pod_mapping:
            print("\nExample:")
            print(f"gossip-0 -> IP: {pod_mapping['gossip-0'][0]}, Index: {pod_mapping['gossip-0'][1]}")
    else:
        print("Pod mapping could not be generated due to errors.")