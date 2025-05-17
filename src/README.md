# simcn
Cloud Native Simulation for validation purpose.

### Implementation Steps

#### Step 1 - Create a network topology (based on ER or BA)
Below is the example on how to create a network overlay of BA/ER network.

```shell
# Create overlay networkDeployments. Change the values accordingly
$ python network_constructor.py --model BA --nodes 1000 --others 4
Initial status from the input .....
Number of nodes in the network: 1000
Average neighbor (degree): 4
Creating BARABASI ALBERT (BA) network model .....
Average degree: 7.968
Target degree:4
nx.is_connected(network): True
Graph Before: Graph with 1000 nodes and 3984 edges
BA network model is SUCCESSFUL ! ....
Graph After: Graph with 1000 nodes and 3984 edges
Do you want to save the graph? (y/n): y
Topology saved to nodes1000_May172025154908_BA4.json
```
The parameters are as follows:-  
model - BA or ER   
nodes - total number of nodes  
others - for BA, it is edges per new nod . For ER, ranges from 0 to 1 (probability)  

#### Step 2 - Build Deployment or Platform (manually)
**Remember to create a kubernetes cluster before starting Step 2. If not, this script cannot be running.  

In this step, we will use helm. The command is shown below.  
The parameters are as follows:-  
totalNodes - how many nodes for the test. Make sure the total nodes declare the same as json topology (from Step 1).    
image tag - version of the container image.    
```shell
# Deployments. Change the values accordingly
$ helm install simcn ./chartsim --set testType=default,totalNodes=10,image.tag=v7 --debug
install.go:225: 2025-05-17 11:14:17.764061017 +0000 UTC m=+0.054319944 [debug] Original chart version: ""
install.go:242: 2025-05-17 11:14:17.764149208 +0000 UTC m=+0.054408140 [debug] CHART PATH: /home/wwiras/simcn/src/chartsim

client.go:142: 2025-05-17 11:14:21.13904755 +0000 UTC m=+3.429306464 [debug] creating 4 resource(s)
NAME: simcn
LAST DEPLOYED: Sat May 17 11:14:19 2025
NAMESPACE: default
STATUS: deployed
REVISION: 1
TEST SUITE: None
USER-SUPPLIED VALUES:
image:
  tag: v7
testType: default
totalNodes: 10

COMPUTED VALUES:
bandwidth: 5M
image:
  name: wwiras/simcn
  tag: v7
memory:
  limits: 150Mi
  requests: 120Mi
testType: default
totalNodes: 10

HOOKS:
MANIFEST:
---
# Source: chartsim/templates/rbac.yaml
kind: ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: pods-list
rules:
- apiGroups: [""]
  resources: ["pods", "services", "endpoints"]
  verbs: ["list", "get"]
- apiGroups: ["cilium.io"]
  resources: ["ciliumnetworkpolicies"]
  verbs: ["create", "get", "list", "update", "watch", "delete"]
---
# Source: chartsim/templates/rbac.yaml
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: pods-list-binding
subjects:
- kind: ServiceAccount
  name: default
  namespace: default
roleRef:
  kind: ClusterRole
  name: pods-list
  apiGroup: rbac.authorization.k8s.io
---
# Source: chartsim/templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: bcgossip-svc
  labels:
    run: bcgossip
spec:
  ports:
  - port: 5050
    protocol: TCP
  selector:
    run: bcgossip
---
# Source: chartsim/templates/deployment.yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gossip-dpymt
spec:
  replicas: 10
  selector:
    matchLabels:
      app: bcgossip
  template:
    metadata:
      labels:
        app: bcgossip
    spec:
      containers:
        - name: gossip-node
          image: wwiras/simcn:v7
          ports:
            - containerPort: 5050
          env:
            - name: NODES
              value: "10"


```


#### Step 3 -Preparing Network Topology (overlay for BA or ER model) on top of Kubernetes
```shell
# Create overlay networkDeployments. Change the values accordingly
$ python prepare.py --filename nodes10_May152025191119_ER0.6.json
Deployment number of nodes equal to topology nodes: 10
Starting update for 10 pods...
Progress: 100.0% | Elapsed: 18.2s | Success: 10/10 | Failed: 0
Update completed in 18.2 seconds
Summary - Total: 10 | Success: 10 | Failed: 0
Platform is now ready for testing..!
```
As noted in Step 2, the total nodes created for the deployment must be the same as nodes in json topology file.
If not equal, this script will reject the preparation phase. 

#### Step 4 - Gossip Test Automation

After that, proceed gossip test as shown command below. Just indicate how many round of tests.

```shell
$ python automate.py --num_tests 1
self.num_tests=1
Number of running pods (num_nodes): 10
Checking for pods in namespace default...
All 10 pods are up and running in namespace default.
Selected pod: gossip-dpymt-b596cf59f-k5sf8
{"event": "gossip_start", "pod_name": "gossip-dpymt-b596cf59f-k5sf8", "message": "fff7-cubaan10-1", "start_time": "2025/05/17 18:35:29", "details": "Gossip propagation started for message: fff7-cubaan10-1"}
host_ip=10.116.5.47

target=10.116.5.47:5050

Sending message to self (10.116.5.47): 'fff7-cubaan10-1'

Received acknowledgment: Done propagate! 10.116.5.47 received: 'fff7-cubaan10-1'

{"event": "gossip_end", "pod_name": "gossip-dpymt-b596cf59f-k5sf8", "message": "fff7-cubaan10-1", "end_time": "2025/05/17 18:35:32", "details": "Gossip propagation completed for message: fff7-cubaan10-1"}
Test 1 complete.
```

### Step 4 - Platform shutdown (manually)
The command below will shutdown the deployment. You can also shutdown the kubernetes cluster as well if needed.
```shell
$ helm uninstall simcn
release "simcn" uninstalled
```