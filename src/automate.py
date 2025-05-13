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


class Test:
    def __init__(self, num_tests, helm_args):
        # Getting test details
        self.num_tests = num_tests
        self.helm_args = helm_args  # Store Helm arguments as a dictionary
        self.gossip_delay = float(helm_args.get('gossipDelay', 5.0))  # Default 2s
        print(f"self.num_tests = {self.num_tests}", flush=True)
        print(f'self.helm_args = {self.helm_args}', flush=True)

    def run_command(self, command, full_path=None, suppress_output=False):
        """
        Runs a command and handles its output and errors.
        """
        try:
            if isinstance(command, str):
                result = subprocess.run(command, check=True, text=True, capture_output=True, shell=True)
            else:
                result = subprocess.run(command, check=True, text=True, capture_output=True)

            if full_path:
                if 'unchanged' in result.stdout or 'created' in result.stdout:
                    print(f"{full_path} applied successfully!", flush=True)
                elif 'deleted' in result.stdout:
                    print(f"{full_path} deleted successfully!", flush=True)
                else:
                    print(f"Changes applied to {full_path}:", flush=True)
                    print(result.stdout, flush=True)

            if not suppress_output:
                print(f"result.stdout: {result.stdout}", flush=True)

            return result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            if full_path:
                print(f"An error occurred while applying {full_path}.", flush=True)
            else:
                print(f"An error occurred while executing the command.", flush=True)
            print(f"Error message: {e.stderr}", flush=True)
            traceback.print_exc()
            sys.exit(1)
        except Exception as e:
            if full_path:
                print(f"An unexpected error occurred while applying {full_path}.", flush=True)
            else:
                print(f"An unexpected error occurred while executing the command.", flush=True)
            traceback.print_exc()
            sys.exit(1)

    def wait_for_pods_to_be_ready(self, namespace='default', expected_pods=0, timeout=1000):
        """
        Waits for all pods in the specified namespace to be ready.
        """
        print(f"Checking for pods in namespace {namespace}...", flush=True)
        start_time = time.time()
        get_pods_cmd = f"kubectl get pods -n {namespace} --no-headers | grep Running | wc -l"

        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(get_pods_cmd, shell=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                running_pods = int(result.stdout.strip())
                if running_pods >= expected_pods:
                    print(f"All {expected_pods} pods are up and running in namespace {namespace}.", flush=True)
                    return True
                else:
                    print(f" {running_pods} pods are up for now in namespace {namespace}. Waiting...", flush=True)
            except subprocess.CalledProcessError as e:
                print(f"Error checking for pods: {e.stderr}", flush=True)
                return False
            time.sleep(1)
        print(f"Timeout waiting for pods to terminate in namespace {namespace}.", flush=True)
        return False

    def wait_for_pods_to_be_down(self, namespace='default', timeout=1000):
        """
        Waits for all pods in the specified namespace to be down.
        """
        print(f"Checking for pods in namespace {namespace}...", flush=True)
        start_time = time.time()
        get_pods_cmd = f"kubectl get pods -n {namespace} --no-headers | grep Terminating | wc -l"

        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(get_pods_cmd, shell=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if "No resources found" in result.stderr:
                    print(f"No pods found in namespace {namespace}.", flush=True)
                    return True
                else:
                    print(f"Pods still exist in namespace {namespace}. Waiting...", flush=True)
            except subprocess.CalledProcessError as e:
                print(f"Error checking for pods: {e.stderr}", flush=True)
                return False
            time.sleep(1)
        print(f"Timeout waiting for pods to terminate in namespace {namespace}.", flush=True)
        return False

    def get_num_nodes(self, namespace='default'):
        """
        Dynamically determines the number of nodes (pods) by counting running pods.
        """
        get_pods_cmd = f"kubectl get pods -n {namespace} --no-headers | grep Running | wc -l"
        try:
            result = subprocess.run(get_pods_cmd, shell=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            num_nodes = int(result.stdout.strip())
            print(f"Number of running pods (num_nodes): {num_nodes}", flush=True)
            return num_nodes
        except subprocess.CalledProcessError as e:
            print(f"Error getting number of pods: {e.stderr}", flush=True)
            return 0

    def select_random_pod(self):
        """
        Select a random pod from the list of running pods.
        """
        command = "kubectl get pods --no-headers | grep Running | awk '{print $1}'"
        stdout, stderr = self.run_command(command, suppress_output=True)
        pod_list = stdout.split()
        if not pod_list:
            raise Exception("No running pods found.")
        return random.choice(pod_list)

    def _get_malaysian_time(self):
        """Helper function to get the current time in Malaysian timezone (UTC+8)."""
        utc_time = datetime.now(timezone.utc)
        malaysia_offset = timedelta(hours=8)
        malaysia_time = utc_time + malaysia_offset
        return malaysia_time

    def access_pod_and_initiate_gossip(self, pod_name, replicas, unique_id, iteration):
        """
        Access the pod's shell, initiate gossip, and handle the response.
        """

        time.sleep(self.gossip_delay)  # Use configurable delay

        try:
            start_time = self._get_malaysian_time().strftime('%Y/%m/%d %H:%M:%S')
            message = f'{unique_id}-cubaan{replicas}-{iteration}'
            start_log = {
                'event': 'gossip_start',
                'pod_name': pod_name,
                'message': message,
                'start_time': start_time,
                'details': f"Gossip propagation started for message: {message}"
            }
            print(json.dumps(start_log), flush=True)

            session = subprocess.Popen(['kubectl', 'exec', '-it', pod_name, '--request-timeout=3000',
                                       '--', 'sh'], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            session.stdin.write(f'python3 start.py --message {message}\n')
            session.stdin.flush()

            end_time = time.time() + 3000
            while time.time() < end_time:
                reads = [session.stdout.fileno()]
                ready = select.select(reads, [], [], 5)[0]
                if ready:
                    output = session.stdout.readline()
                    print(output, flush=True)
                    if 'Received acknowledgment:' in output:
                        end_time_log = self._get_malaysian_time().strftime('%Y/%m/%d %H:%M:%S')
                        end_log = {
                            'event': 'gossip_end',
                            'pod_name': pod_name,
                            'message': message,
                            'end_time': end_time_log,
                            'details': f"Gossip propagation completed for message: {message}"
                        }
                        print(json.dumps(end_log), flush=True)
                        break
                if session.poll() is not None:
                    print("Session ended before completion.", flush=True)
                    break
            else:
                print("Timeout waiting for gossip to complete.", flush=True)
                return False

            session.stdin.write('exit\n')
            session.stdin.flush()
            return True

        except Exception as e:
            error_log = {
                'event': 'gossip_error',
                'pod_name': pod_name,
                'message': message,
                'error': str(e),
                'details': f"Error accessing pod {pod_name}: {e}"
            }
            print(json.dumps(error_log), flush=True)
            traceback.print_exc()
            return False


if __name__ == '__main__':
    # Parse arguments
    parser = argparse.ArgumentParser(description="Usage: python automate.py --num_tests <number_of_tests> --set key1=value1 key2=value2 ...")
    parser.add_argument('--num_tests', required=True, type=int, help="Total number of tests to do")
    parser.add_argument('--set', action='append', help="Helm --set arguments in key=value format", default=[])
    args = parser.parse_args()

    # Convert --set arguments into a dictionary
    helm_args = {}
    for s in args.set:
        key, value = s.split('=', 1)
        helm_args[key] = value

    # Ensure totalNodes is provided or set a default value
    if 'totalNodes' not in helm_args:
        print("Warning: totalNodes not provided. Using default value: totalNodes=10", flush=True)
        helm_args['totalNodes'] = '10'  # Set default value

    # Confirm totalNodes value
    total_nodes = helm_args.get('totalNodes')
    if not total_nodes or not total_nodes.isdigit():
        print("Error: totalNodes must be a valid integer.", flush=True)
        sys.exit(1)

    print(f"totalNodes confirmed: {total_nodes}", flush=True)

    test = Test(args.num_tests, helm_args)  # Pass the Helm arguments to Test

    # Helm name is fixed
    helmname = 'cnsim'

    if test.wait_for_pods_to_be_down(namespace='default', timeout=1000):
        # Build the Helm install command
        helm_command = ['helm', 'install', helmname, './chartsim', '--debug']
        for key, value in helm_args.items():
            helm_command.extend(['--set', f'{key}={value}'])

        # Apply Helm
        result = test.run_command(helm_command)
        print(f"Helm {helmname} started...", flush=True)

        # Wait for pods to be ready
        if test.wait_for_pods_to_be_ready(namespace='default', expected_pods=int(total_nodes), timeout=1000):
            unique_id = str(uuid.uuid4())[:4]

            # Test iteration starts here
            for nt in range(0, test.num_tests + 1):
                pod_name = test.select_random_pod()
                print(f"Selected pod: {pod_name}", flush=True)
                if test.access_pod_and_initiate_gossip(pod_name, int(total_nodes), unique_id, nt):
                    print(f"Test {nt} complete.", flush=True)
                else:
                    print(f"Test {nt} failed.", flush=True)
        else:
            print(f"Failed to prepare pods for {helmname}.", flush=True)

        # Remove Helm
        result = test.run_command(['helm', 'uninstall', helmname])
        print(f"Helm {helmname} will be uninstalled...", flush=True)
        if test.wait_for_pods_to_be_down(namespace='default', timeout=1000):
            print(f"Helm {helmname} uninstallation is complete...", flush=True)
    else:
        print(f"No file was found for args={args}")