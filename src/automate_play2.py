import argparse
import json
import subprocess
import sys
import traceback
import os  # Import the os module

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
    live_pods = get_live_pods()

    # 3. Create mapping with JSON indices
    pod_map = {}
    for idx, node in enumerate(topology['nodes']):
        pod_name = node['id']
        pod_map[pod_name] = (
            live_pods.get(pod_name, "UNASSIGNED"),  # IP
            idx  # JSON index
        )

    return pod_map


def get_live_pods() -> Dict[str, str]:
    """Fetches {pod_name: pod_ip} from Kubernetes"""
    cmd = [
        'kubectl',
        'get', 'pods',
        '-l', 'app=bcgossip',
        '-o', 'jsonpath={range .items[*]}{.metadata.name}{" "}{.status.podIP}{"\\n"}{end}'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    return dict(line.split() for line in result.stdout.splitlines() if line)


# Example Usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get pod mapping based on topology.")
    parser.add_argument("filename", help="Name of the topology JSON file in the 'topology' folder.")
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