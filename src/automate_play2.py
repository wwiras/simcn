import json
import subprocess
from typing import Dict, List, Tuple


def get_pod_mapping(topology_file: str) -> Dict[str, Tuple[str, int]]:
    """
    Returns:
        {
            "gossip-0": ("10.1.0.1", 0),
            "gossip-1": ("10.1.0.2", 1),
            ...
        }
    """
    # 1. Load topology JSON
    with open(topology_file) as f:
        topology = json.load(f)

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
    pod_mapping = get_pod_mapping("nodes10_May152025191119_ER0.6.json")

    print("Pod Name\tIP Address\tJSON Index")
    print("-" * 40)
    for name, (ip, idx) in pod_mapping.items():
        print(f"{name}\t{ip}\t{idx}")

    # Access specific pod
    print("\nExample:")
    print(f"gossip-0 -> IP: {pod_mapping['gossip-0'][0]}, Index: {pod_mapping['gossip-0'][1]}")