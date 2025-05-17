# simcn
Cloud Native Simulato
This code will be used to simulate gossip protocol in blockchain network.

### Implementation Steps

#### Step 1 - Create a network topology (based on ER or BA)

Below is the example on how to create a network overlay of BA/ER network

```shell
# Create overlay networkDeployments. Change the values accordingly
python network_constructor.py --model BA --nodes 1000 --others 4
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
The parameter is as follows:-
model - BA or ER 
nodes - total number of nodes
others - for BA, it is edges per new node
       - for ER, ranges from 0 to 1 (probability)

#### Step 2 - Build Deployment or Platform (manually)
In this step, we will use helm.
```shell
# Deployments. Change the values accordingly
helm install simcn ./chartsim --set testType=default,totalNodes=10,image.tag=v7 --debug
```
totalNodes - how many nodes for the test. Make sure it is according to json topology
image tag - version of the container image

#### Step 3 - Build Network (overlay for BA or ER model) -from Step 1 output
```shell
# Create overlay networkDeployments. Change the values accordingly
python prepare.py --filename nodes100_May162025222410_BA2.json
# Output example
Starting update for 100 pods...
Progress: 100.0% | Elapsed: 177.1s | Success: 100/100 | Failed: 0
Update completed in 177.1 seconds
Summary - Total: 100 | Success: 100 | Failed: 0
Platform is now ready for testing..!
```
As noted in Step 2, the total nodes created for the deployment must be the same as nodes in json topology file

#### Step 4 - Gossip Test Automation

### Step 4 - Platform shutdown (manually)