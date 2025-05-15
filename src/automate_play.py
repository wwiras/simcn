import subprocess
import json
from typing import Dict


def get_pod_info() -> Dict[str, str]:
    """
    Fetches pod names and IPs from Kubernetes and returns them as a dictionary.

    Returns:
        Dict[str, str]: {pod_name: pod_ip} mapping
    """
    try:
        # Run kubectl command to get pod info in JSON format
        cmd = [
            'kubectl',
            'get',
            'pods',
            '-l', 'app=bcgossip',  # Filter by your label
            '-o', 'json',
            '--field-selector=status.phase=Running'  # Only running pods
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse JSON output
        pod_data = json.loads(result.stdout)

        # Create {pod_name: pod_ip} dictionary
        pod_info = {
            pod['metadata']['name']: pod['status']['podIP']
            for pod in pod_data['items']
            if pod['status'].get('podIP')  # Only include pods with IPs
        }

        return pod_info

    except subprocess.CalledProcessError as e:
        print(f"Error running kubectl: {e.stderr}")
        return {}
    except json.JSONDecodeError:
        print("Error parsing kubectl output")
        return {}
    except KeyError:
        print("Unexpected JSON structure from kubectl")
        return {}


# Example usage
if __name__ == "__main__":
    pods = get_pod_info()
    print("Current Pods and IPs:")
    for name, ip in pods.items():
        print(f"{name}: {ip}")

    # Store in memory for your application to use
    # Example: Access