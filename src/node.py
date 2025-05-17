from kubernetes import client, config
import grpc
import os
import socket
from concurrent import futures
import gossip_pb2
import gossip_pb2_grpc
import json
import time
import sqlite3

# Inspired from k8sv2
class Node(gossip_pb2_grpc.GossipServiceServicer):

    def __init__(self, service_name):
        self.hostname = socket.gethostname()
        self.host = socket.gethostbyname(self.hostname)
        self.port = '5050'
        self.service_name = service_name
        self.app_name = 'bcgossip'
        # List to keep track of IPs of neighboring nodes
        self.susceptible_nodes = []
        # Set to keep track of messages that have been received to prevent loops
        self.received_message = ""
        # self.gossip_initiated = False

    def get_neighbors(self):

        try:
            # Connecting to sqlite
            conn = sqlite3.connect('ned.db')

            # SELECT table
            cursor = conn.execute("SELECT pod_ip from NEIGHBORS")

            # Clear the existing list to refresh it
            self.susceptible_nodes = []

            for row in cursor:
                self.susceptible_nodes.append(row[0])
            # print(f"self.susceptible_nodes: {self.susceptible_nodes}")
            conn.close()

        except sqlite3.Error as e:
            print(f"SQLite error: {e}")

    def SendMessage(self, request, context):

        """
        Receiving message from other nodes
        and distribute it to others (multi rounds gossip)
        """
        message = request.message
        sender_id = request.sender_id
        received_timestamp = time.time_ns()

        # For initiating acknowledgment only
        if sender_id == self.host:
            self.received_message = message
            log_message = (f"Gossip initiated by {self.hostname} ({self.host}) at "
                           f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(received_timestamp / 1e9))}")
            self._log_event(message, sender_id, received_timestamp, None,
                            'initiate', log_message)
            self.gossip_message(message, sender_id)
            return gossip_pb2.Acknowledgment(details=f"Done propagate! {self.host} received: '{message}'")

        # Check whether the message is already received ot not
        # Notify whether accept it or ignore it
        elif self.received_message == message:
            log_message = f"{self.host} ignoring duplicate message: {message} from {sender_id}"
            self._log_event(message, sender_id, received_timestamp, None, 'duplicate', log_message)
            return gossip_pb2.Acknowledgment(details=f"Duplicate message ignored by ({self.host})")
        else:
            self.received_message = message
            propagation_time = (received_timestamp - request.timestamp) / 1e6
            log_message = (f"({self.hostname}({self.host}) received: '{message}' from {sender_id}"
                           f" in {propagation_time:.2f} ms ")
            self._log_event(message, sender_id, received_timestamp, propagation_time, 'received', log_message)
            # Start gossip only when the node is the gossip initiator itself
            # therefore, only one iteration is required

            # gossip to its neighbor (if this pod is not the initiator)
            self.gossip_message(message, sender_id)

            return gossip_pb2.Acknowledgment(details=f"{self.host} received: '{message}'")

    def gossip_message(self, message, sender_ip):
        # Refresh list of neighbors before gossiping to capture any changes
        if len(self.susceptible_nodes) == 0:
            self.get_neighbors()
        print(f"self.susceptible_nodes: {self.susceptible_nodes}",flush=True)


        # for peer_name, peer_ip in self.susceptible_nodes: # we don't need hostname yet
        for peer_ip in self.susceptible_nodes:
            # Exclude the sender from the list of nodes to forward the message to
            if peer_ip != sender_ip:

                # Record the send timestamp
                send_timestamp = time.time_ns()

                with grpc.insecure_channel(f"{peer_ip}:5050") as channel:
                    try:
                        stub = gossip_pb2_grpc.GossipServiceStub(channel)
                        stub.SendMessage(gossip_pb2.GossipMessage(
                            message=message,
                            sender_id=self.host,
                            timestamp=send_timestamp,
                        ))
                    except grpc.RpcError as e:
                        print(f"Failed to send message: '{message}' to {peer_ip}: {e}", flush=True)

    def _log_event(self, message, sender_id, received_timestamp, propagation_time, event_type, log_message):
        """Logs the gossip event as structured JSON data."""
        event_data = {
            'message': message,
            'sender_id': sender_id,
            'receiver_id': self.host,
            'received_timestamp': received_timestamp,
            'propagation_time': propagation_time,
            'event_type': event_type,
            'detail': log_message
        }

        # Print both the log message and the JSON data to the console
        print(json.dumps(event_data), flush=True)

    def start_server(self):
        """ Initiating server """
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        gossip_pb2_grpc.add_GossipServiceServicer_to_server(self, server)
        server.add_insecure_port(f'[::]:{self.port}')
        print(f"{self.hostname}({self.host}) listening on port {self.port}", flush=True)
        server.start()
        server.wait_for_termination()

def run_server():
    service_name = os.getenv('SERVICE_NAME', 'bcgossip-svc')
    node = Node(service_name)
    node.start_server()

if __name__ == '__main__':
    run_server()