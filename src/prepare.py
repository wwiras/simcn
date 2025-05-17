import argparse
import json
import subprocess
import sys
import os  # Import the os module
from typing import Dict, List, Tuple  # Import Dict and Tuple from typing

### Latest amendment
def get_pod_topology(topology_folder, filename):
    """
    Function : It will read the topology (from a given json file - network topology)
    Input: Topology folder name and filename
    Returns: topology object - if found. False, if not found
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
        topology = False

    return topology

def get_pod_neighbors(topology):
    """
    Creates a dictionary mapping each node to its neighbors.

    Args:
        topology: The topology dictionary containing 'nodes' and 'edges'

    Returns:
        Dictionary {node_id: [neighbor1, neighbor2, ...]}
    """
    neighbor_map = {node['id']: [] for node in topology['nodes']}

    for edge in topology['edges']:
        source = edge['source']
        target = edge['target']

        # Add bidirectional connections for undirected graphs
        neighbor_map[source].append(target)
        if not topology['directed']:
            neighbor_map[target].append(source)

    return neighbor_map

def get_pod_dplymt():
    """
    Fetches [(index, pod_name, pod_ip)] from Kubernetes or returns False on failure.

    Returns:
        - List of (index, pod_name, pod_ip) tuples on success
        - False on any failure
    """
    cmd = [
        'kubectl',
        'get', 'pods',
        '-l', 'app=bcgossip',
        '-o', 'jsonpath={range .items[*]}{.metadata.name}{" "}{.status.podIP}{"\\n"}{end}'
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            text=True,
            capture_output=True,
            timeout=10
        )

        if not result.stdout.strip():
            print("Error: No pods found with label app=bcgossip")
            return False

        pods_data = [line.split() for line in result.stdout.splitlines() if line]
        pods_data.sort(key=lambda x: x[0])  # Sort by pod name

        # Add index to each pod entry
        return [(i, name, ip) for i, (name, ip) in enumerate(pods_data)]

    except subprocess.CalledProcessError as e:
        print(f"kubectl failed (exit {e.returncode}): {e.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print("Error: kubectl command timed out after 10 seconds")
        return False
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return False

def get_pod_mapping(pod_deployment, pod_neighbors):
    """
    Creates {deployment_pod_name: [(neighbor_ip,), ...]} mapping

    Args:
        pod_deployment: List of (index, pod_name, pod_ip) tuples
        pod_neighbors: Dict {'gossip-0': ['gossip-1', ...], ...}

    Returns:
        Dict {deployment_pod_name: [('ip1',), ('ip2',), ...]}
    """
    # Create lookup dictionaries
    gossip_id_to_ip = {f'gossip-{index}': ip for index, _, ip in pod_deployment}
    # deployment_names = {f'gossip-{index}': name for index, name, _ in pod_deployment}

    result = {}

    for index, deployment_name, _ in pod_deployment:
        gossip_id = f'gossip-{index}'
        if gossip_id in pod_neighbors:
            # Get IPs of all neighbors
            neighbor_ips = [
                (gossip_id_to_ip[neighbor],)
                for neighbor in pod_neighbors[gossip_id]
                if neighbor in gossip_id_to_ip
            ]
            result[deployment_name] = neighbor_ips

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get pod mapping and neighbor info based on topology.")
    parser.add_argument("--filename", help="Name of the topology JSON file in the 'topology' folder.")
    parser.add_argument("--topology_folder", default="topology", help="Name of the topology folder from the root.")
    args = parser.parse_args()

    # prepare flag
    prepare = False

    # 1. Get topology from json
    pod_topology = get_pod_topology(args.topology_folder, args.filename)
    print(f"Pod topology - {pod_topology}")

    if pod_topology:

        # 2. Get pod topology neighbors
        pod_neighbors = get_pod_neighbors(pod_topology)
        print(f"pod_neighbors - {pod_neighbors}")

        # 3. Get pods info from deployment
        pod_dplymt = get_pod_dplymt()
        print(f"Pod deployment - {pod_dplymt}")

        # 4. Get pod mapping with tuples
        pod_mapping = get_pod_mapping(pod_dplymt, pod_neighbors)
        print(f"Pod mapping - {pod_mapping}")

