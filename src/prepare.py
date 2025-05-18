import argparse
import json
import subprocess
import sys
import os  # Import the os module
import time


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

def get_num_nodes(namespace='default'):
    """
    Dynamically determines the number of nodes (pods) by counting running pods.
    """
    get_pods_cmd = f"kubectl get pods -n {namespace} --no-headers | grep Running | wc -l"
    try:
        result = subprocess.run(get_pods_cmd, shell=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        num_nodes = int(result.stdout.strip())
        # print(f"Number of running pods (num_nodes): {num_nodes}", flush=True)
        return num_nodes
    except subprocess.CalledProcessError as e:
        print(f"Error getting number of pods: {e.stderr}", flush=True)
        return False

def update_pod_neighbors(pod, neighbors, timeout=300):  # Increased timeout to 5 minutes
    """
    Atomically updates neighbor list in a pod's SQLite DB.
    Returns (success: bool, output: str) tuple in ALL cases.
    """
    try:
        # 1. Convert neighbors to JSON-safe format
        ip_list = [ip for (ip,) in neighbors]
        neighbors_json = json.dumps(ip_list)

        # 2. Create properly escaped Python command
        python_script = f"""
import sqlite3
import json

try:
    values = [(ip,) for ip in json.loads('{neighbors_json.replace("'", "\\'")}')]
    with sqlite3.connect('ned.db') as conn:
        conn.execute('BEGIN TRANSACTION')
        conn.execute('DROP TABLE IF EXISTS NEIGHBORS')
        conn.execute('CREATE TABLE NEIGHBORS (pod_ip TEXT PRIMARY KEY)')
        conn.executemany('INSERT INTO NEIGHBORS VALUES (?)', values)
        conn.commit()
    print(f"Updated {{len(values)}} neighbors")
except Exception as e:
    print(f"Error: {{str(e)}}")
    raise
"""

        # 3. Execute via kubectl with proper quoting
        cmd = [
            'kubectl', 'exec', pod,
            '--', 'python3', '-c', python_script
        ]

        result = subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=timeout)
        return True, result.stdout.strip()

    except subprocess.CalledProcessError as e:
        return False, f"Command failed: {e.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout} seconds"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

# progress update for each pod
# def update_pod_neighbors2(pod, neighbors):
#     """
#     Atomically updates neighbor list in a pod's SQLite DB.
#
#     Args:
#         pod: Pod name (e.g. 'gossip-0')
#         neighbors: List of (ip,) tuples like [('10.44.1.4',), ...]
#     """
#     # 1. Convert neighbors to JSON-safe format
#     ip_list = [ip for (ip,) in neighbors]
#     neighbors_json = json.dumps(ip_list)
#
#     # 2. Create properly escaped Python command
#     python_script = f"""
# import sqlite3
# import json
#
# try:
#     values = [(ip,) for ip in json.loads('{neighbors_json.replace("'", "\\'")}')]
#     with sqlite3.connect('ned.db') as conn:
#         conn.execute('BEGIN TRANSACTION')
#         conn.execute('DROP TABLE IF EXISTS NEIGHBORS')
#         conn.execute('CREATE TABLE NEIGHBORS (pod_ip TEXT PRIMARY KEY)')
#         conn.executemany('INSERT INTO NEIGHBORS VALUES (?)', values)
#         conn.commit()
#     print(f"Updated {{len(values)}} neighbors")
# except Exception as e:
#     print(f"Error: {{str(e)}}")
#     raise
# """
#
#     # 3. Execute via kubectl with proper quoting
#     cmd = [
#         'kubectl', 'exec', pod,
#         '--', 'python3', '-c', python_script
#     ]
#
#     try:
#         result = subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=30)
#         print(result.stdout)
#         return True
#     except subprocess.CalledProcessError as e:
#         print(f"Failed to update {pod}: {e.stderr}")
#         return False

def update_all_pods(pod_mapping, max_retries=3, initial_timeout=300):
    """
    Update neighbors for all pods with extended timeout and retry capabilities

    Args:
        pod_mapping: Dictionary of pod to neighbors mapping
        max_retries: Number of retry attempts for failed updates
        initial_timeout: Initial timeout in seconds (will increase with retries)
    """
    pod_list = list(pod_mapping.keys())
    total_pods = len(pod_list)
    success_count = 0
    failure_count = 0
    start_time = time.time()
    retry_queue = []

    print(f"\nStarting update for {total_pods} pods (timeout: {initial_timeout}s, max retries: {max_retries})...")

    # First attempt
    for i, pod in enumerate(pod_list, 1):
        neighbors = pod_mapping.get(pod, [])
        timeout = initial_timeout

        success, output = update_pod_neighbors(pod, neighbors, timeout)

        if success:
            success_count += 1
        else:
            retry_queue.append((pod, neighbors, 1))  # Track retry count
            failure_count += 1
            print(f"\nInitial attempt failed for {pod}: {output}")

        # Progress reporting
        elapsed = time.time() - start_time
        progress = (i / total_pods) * 100
        print(
            f"\rProgress: {progress:.1f}% | "
            f"Elapsed: {elapsed:.1f}s | "
            f"Success: {success_count}/{total_pods} | "
            f"Failed: {failure_count} | "
            f"Retries pending: {len(retry_queue)}",
            end='', flush=True
        )

    # Retry logic
    while retry_queue and (time.time() - start_time) < 3600:  # 1 hour max total runtime
        pod, neighbors, retry_count = retry_queue.pop(0)
        timeout = initial_timeout * (retry_count + 1)  # Exponential backoff

        print(f"\nRetry #{retry_count} for {pod} (timeout: {timeout}s)...")
        success, output = update_pod_neighbors(pod, neighbors, timeout)

        if success:
            success_count += 1
            failure_count -= 1
        elif retry_count < max_retries:
            retry_queue.append((pod, neighbors, retry_count + 1))
            print(f"Retry failed for {pod}: {output}")
        else:
            print(f"Max retries exceeded for {pod}")

        # Update progress
        elapsed = time.time() - start_time
        progress = (success_count / total_pods) * 100
        print(
            f"\rProgress: {progress:.1f}% | "
            f"Elapsed: {elapsed:.1f}s | "
            f"Success: {success_count}/{total_pods} | "
            f"Failed: {failure_count} | "
            f"Retries pending: {len(retry_queue)}",
            end='', flush=True
        )

    # Final summary
    total_time = time.time() - start_time
    print(f"\n\nUpdate completed in {total_time:.1f} seconds")
    print(f"Summary - Total: {total_pods} | Success: {success_count} | Failed: {failure_count}")

    return success_count == total_pods

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get pod mapping and neighbor info based on topology.")
    parser.add_argument("--filename", help="Name of the topology JSON file in the 'topology' folder.")
    parser.add_argument("--topology_folder", default="topology", help="Name of the topology folder from the root.")
    args = parser.parse_args()

    # prepare flag
    prepare = False

    # 1. Get topology from json
    pod_topology = get_pod_topology(args.topology_folder, args.filename)
    # print(f"Pod topology - {pod_topology}")

    if pod_topology:

        # 2. Make sure topology nodes are the same as deployment nodes
        nodes_dplymt = get_num_nodes()
        # print(f"Number of nodes deployment: {nodes_dplymt}")

        nodes_topology = len(pod_topology['nodes'])
        # print(f"Number of nodes topology: {nodes_topology}")

        if nodes_topology == nodes_dplymt:

            print(f"Deployment number of nodes equal to topology nodes: {nodes_topology}")
            # 3. Get pod topology neighbors
            if pod_topology:
                pod_neighbors = get_pod_neighbors(pod_topology)
                # print(f"pod_neighbors - {pod_neighbors}")

                # 4. Get pods info from deployment
                if pod_neighbors:
                    pod_dplymt = get_pod_dplymt()
                    # print(f"Pod deployment - {pod_dplymt}")

                    # 5. Get pod mapping with tuples
                    if pod_dplymt:
                        pod_mapping = get_pod_mapping(pod_dplymt, pod_neighbors)
                        # print(f"Pod mapping - {pod_mapping}")

                        if pod_mapping:
                            # for pod, neighbors in pod_mapping.items():
                                # print(f"Pod:{pod} - neighbors: {neighbors}")
                                # if update_pod_neighbors2(pod, neighbors):
                                #     print(f"Pod:{pod} neighbors Updated")
                                # else:
                                #     print(f"Pod:{pod} neighbors Not Updated")
                            update_all_pods(pod_mapping)
                            prepare = True

        else:
            print("Error: Deployment number of nodes and topology must be equal.", flush=True)
            sys.exit(1)

    if prepare:
        print("Platform is now ready for testing..!")
    else:
        print("Platform could not be ready due to errors.")

