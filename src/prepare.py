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