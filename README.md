# TopFull (SIGCOMM 2024)

This is an official Github repository for the SIGCOMM '24 paper "TopFull: An Adaptive Top-Down Overload Control for SLO-Oriented Microservices".
The repository includes our implementation of TopFull on microservices environment.

## Setting Kubernetes environment (master node and worker nodes)

Set up Kubernetes environment for a master node and worker nodes.
cAdvisor is necessary for collecting resource usage.
We have used Kubernetes version 1.26.0, Ubuntu version 20.04.6

1. Install cri-docker & environment setup (Master & Worker)

```bash
sudo swapoff -a

curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable --now docker && sudo systemctl status docker --no-pager
sudo usermod -aG docker $USER
sudo docker container ls

# cri-docker Install
VER=$(curl -s https://api.github.com/repos/Mirantis/cri-dockerd/releases/latest|grep tag_name | cut -d '"' -f 4|sed 's/v//g')
echo $VER
wget https://github.com/Mirantis/cri-dockerd/releases/download/v${VER}/cri-dockerd-${VER}.amd64.tgz
tar xvf cri-dockerd-${VER}.amd64.tgz
sudo mv cri-dockerd/cri-dockerd /usr/local/bin/

# cri-docker Version Check
cri-dockerd --version

wget https://raw.githubusercontent.com/Mirantis/cri-dockerd/master/packaging/systemd/cri-docker.service
wget https://raw.githubusercontent.com/Mirantis/cri-dockerd/master/packaging/systemd/cri-docker.socket
sudo mv cri-docker.socket cri-docker.service /etc/systemd/system/
sudo sed -i -e 's,/usr/bin/cri-dockerd,/usr/local/bin/cri-dockerd,' /etc/systemd/system/cri-docker.service

sudo systemctl daemon-reload
sudo systemctl enable cri-docker.service
sudo systemctl enable --now cri-docker.socket

# cri-docker Active Check
sudo systemctl restart docker && sudo systemctl restart cri-docker
sudo systemctl status cri-docker.socket --no-pager

# Docker cgroup Change Require to Systemd
sudo mkdir /etc/docker
cat <<EOF | sudo tee /etc/docker/daemon.json
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m"
  },
  "storage-driver": "overlay2"
}
EOF

sudo systemctl restart docker && sudo systemctl restart cri-docker
sudo docker info | grep Cgroup

# Kernel Forwarding
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
br_netfilter
EOF

cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
EOF

sudo sysctl --system
```

2. Package installation (Master & Worker)

```bash
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl
sudo curl -fsSLo /usr/share/keyrings/kubernetes-archive-keyring.gpg https://dl.k8s.io/apt/doc/apt-key.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.26/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.26/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg


# It acknowledge packages after the update
sudo apt-get update

# Install k8s
sudo apt-get install -y kubelet kubeadm kubectl

# Check version
kubectl version --short

# Fix version
sudo apt-mark hold kubelet kubeadm kubectl
```

3. Cluster Init (Master node)

```bash
sudo kubeadm init --pod-network-cidr 192.168.0.0/16 --service-cidr 10.96.0.0/12 --cri-socket unix://var/run/cri-dockerd.sock

#To start using your cluster, you need to run the following as a regular user:
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

4. CNI installation (Master node)

```bash
cd TopFull/TopFull_master
kubectl apply -f calico.yaml
```

5. cAdvisor (Master node)

```python
# https://github.com/google/cadvisor/tree/master/deploy/kubernetes
cd TopFull/TopFull_master/online_boutique_scripts/cadvisor
$ kubectl kustomize deploy/kubernetes/base | kubectl apply -f -
```

6. Connecting worker nodes 

```bash
# at master node
sudo kubeadm token create --print-join-command
```
```bash
# at worker node
sudo kubeadm join "token_value_from_above" --cri-socket unix://var/run/cri-dockerd.sock
```

7. Check Master & Worker nodes.

```bash
# at master node
kubectl get po --all-namespaces -owide
```
If the above setups are done correctly, it will output similar to the below image.
![image](https://github.com/user-attachments/assets/e5f17966-3b73-4c1e-8c8e-e63a08b4f13b)



## Setting master node and building application images
We run TopFull algorithm that makes load control decisions at the master node. Install the required packages for running the below codes. 

    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src/proxy
    go run proxy_online_boutique.go

    cd TopFull/TopFull_master/online_boutique_scripts/src
    python deploy_rl.py
    python metric_collector.py
    ```
(deploy_rl.py doesn't work without running proxy_online_botique.go and metric_collector.py doesn't work without workload input from the load generator)

download go 1.13.8.linux-amd64 version from 
https://go.dev/doc/install

To find appropriate versions of the packages, refer to **requirements.txt** file in TopFull_master directory. (e.g., ray version 2.0.0)



## Setting up load generation node
Load is generated through Locust from a separate machine. 
We provide bash files for load generation in `TopFull_loadgen` directory. You can configure the desired throughput for each API by modifying the bash files.
Install Locust and the required packages for running the code. 
For the appropriate version of the packages, refer to **requirements.txt** file in TopFull_loadgen directory.
A single locust process cannot use multiple CPU cores. Therefore, multiple processes should be created to generate more users.

You may set a path to run the locust command.
```bash
export PATH=$PATH:/home/topfull-loadgen/.local/bin
```

Test locust is successfully installed and executable.
```bash
cd TopFull/TopFull_loadgen
locust -f locust_online_boutique.py --host=http://10.8.0.22:30440 -u 5 -r 3 --headless  --tags postcheckout < ports/8928
```
The host should match the master node's ip address

In line 293 of `locust_online_boutique.py` set the appropriate IP address of the master node.
```
    def on_start(self):
        self.client.proxies = {"http": "http://10.8.0.22:8090"}
        self.client.verify = False
```


## Setting configurations
You should modify some configuration parameters according to your environment.  
The configuration file for this project is named `TopFull_master/online_boutique_scripts/src/global_config.json`.  
Here is an example of what it looks like and explanations of parameters that should be modified.  

```bash
# TopFull_master/online_boutique_scripts/src/global_config.json
{
    "checkpoint_path": "/home/master_artifact/TopFull/online_boutique_scripts/src/checkpoint_000701",
    "microservice_code": "online_boutique",
    "proxy_dir": "/home/master_artifact/TopFull/online_boutique_scripts/src/proxy/rate_config/",
    "microservice_configuration": "/home/master_artifact/TopFull/online_boutique_scripts/src/config/online_boutique.json",
    "proxy_url": "http://10.8.0.4:8090",
    "locust_url": "http://10.8.0.15",
    "locust_port": 43,
    "record_target": ["getcart", "getproduct", "postcheckout", "postcart", "emptycart"],
    "record_path": "/home/master_artifact/TopFull/online_boutique_scripts/src/logs/",
    "num_instance_path": "/home/master_artifact/TopFull/online_boutique_scripts/src/logs/num_instances.csv",
    "frontend_url": "10.8.0.4:30440"
}
```
* **common**: You should write an appropriate absolute path according to your home directory.  
* **proxy_url**, **frontend_url**: You should modify this parameter into your ip address of master node and appropriate port numbers.
* **locust_url**: You should modify this parameter into your ip address of load generation node.

`TopFull_master/online_boutique_scripts/src/proxy/proxy_online_boutique.go` line 28,
`TopFull_master/online_boutique_scripts/src/deploy_rl.py` line 13,
`TopFull_master/online_boutique_scripts/src/metric_collector.py` line 9,
`TopFull_master/online_boutique_scripts/src/overload_detection.py` line 10,
set the appropriate path to the global_config.json file.

Few configurations are hard coded.
In `TopFull_master/online_boutique_scripts/src/overload_detection.py`, you can set the business priority among APIs in line 25.
In line 115, the CPU quota unit per pod should match the configured value in the yaml file.
In line 456 of `TopFull_master/online_boutique_scripts/src/resource_collector.py` file, the number of exec command should match the number of cAdvisor pods which differ according to the number of the worker nodes (Current setting expects 5 worker nodes).

In **Load Generator** Node, configure the host address to the master node's address in bash files' locust commands.
    ```
    online_boutique_create.sh
    online_boutique_create2.sh
    ```
Change the below host address parts of **"--host=http://10.9.0.4:30440"** to the corresponding master node's address.
```
tmux new-window -d -t session2 "locust -f locust_online_boutique.py **--host=http://10.8.0.4:30440** --tags postcheckout --master-bind-port=8881  --master --expect-workers=10 --headless -u $POSTCHECKOUT -r $((POSTCHECKOUT / RATE)) -t 15m  < ports/8886"
for i in $(seq 1 10)
do
    tmux new-window -d -t session2 "locust -f locust_online_boutique.py **--host=http://10.8.0.4:30440** --tags postcheckout --worker --master-port=8881  --master-host=127.0.0.1 < ports/$((i+8907))"
done
```

Modify resources (number of instances) for microservices through Kubernetes commands and workloads through Locust for the experiment.



## How to run experiments with TopFull

Once all the environments are set up with a master node and worker nodes on Kubernetes, overload experiments are carried out by executing codes in the dedicated order.
Please refer to the below sections first to set up the environments.

1. Deploy microservices and scale instances
   ```
   cd TopFull
   kubectl apply -f TopFull_master/online_boutique_scripts/deployments/online_boutique_original_custom.yaml
   kubectl apply -f TopFull_master/online_boutique_scripts/deployments/metric-server-latest.yaml

   cd TopFull/TopFull_master/online_boutique_scripts/src
   python instance_scaling.py
   ```
   
2. Starting load controller at the master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src/proxy
    go run proxy_online_boutique.go
    ```

3. Running TopFull system (RL ver.) at the master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src
    python deploy_rl.py
    ```

4. Generate API workloads at the load generation node.
    ```
    cd TopFull/TopFull_loadgen
    ./online_boutique_create.sh
    ./online_boutique_create2.sh
    ```

5. Monitor and record results at the master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src
    python metric_collector.py
    ```

## How to run experiments with Breakwater and DAGOR

Breakwater and DAGOR overload control algorithms are implemented by modifying the source code of online boutique application.
We provide the modified codes in the online_boutique_source_code directory.
In the master node, instead of online_boutique_original_custom.yaml,
execute online_boutique_breakwater_custom.yaml and online_boutique_dagor_custom.yaml.

1. Deploy microservices and scale instances
   ```
   cd TopFull
   kubectl apply -f TopFull_master/online_boutique_scripts/deployments/online_boutique_breakwater_custom.yaml
   kubectl apply -f TopFull_master/online_boutique_scripts/deployments/metric-server-latest.yaml
   
   cd TopFull/TopFull_master/online_boutique_scripts/src
   python instance_scaling.py
   ```

2. Starting load controller at the master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src/proxy
    go run proxy_online_boutique.go
    ```

3. Generate API workloads at the load generation node.
    ```
    cd TopFull/TopFull_loadgen
    ./online_boutique_create.sh
    ./online_boutique_create2.sh
    ```

4. Monitor and record results at the master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src
    python metric_collector.py
    ```

## Running component-wise experiments 

For component-wise experiments (corresponding to Figure 10 in the paper), instead of deploy_rl.py run deploy_mimd.py, or deploy_without_cluster.py. as below.
deploy_mimd.py corresponds to TopFull with a heuristic MIMD-based rate controller instead of an RL-based rate controller.

    
    cd TopFull/TopFull_master/online_boutique_scripts/src
    python deploy_mimd.py
    
deploy_without_cluster.py corresponds to TopFull disabled with clustering APIs for parallel load control. 

    
    cd TopFull/TopFull_master/online_boutique_scripts/src
    python deploy_without_cluster.py
    

## Generating traffic surge

For traffic surge generation (corresponding to Figure 14, 15 in the paper) we provide the load generation bash scripts we have used.
At the load generation node, first, generate base load which should be adequate workloads that microservices can handle.

    
    cd TopFull/TopFull_loadgen
    ./run_fig14_train_ticket_base.sh
    
    
Next, run below to generate a traffic surge scenario.

    
    cd TopFull/TopFull_loadgen
    ./run_fig14_train_ticket.sh
    
    
For the online boutique application, do same with ```run_fig15_online_boutique_base.sh, run_fig15_online_boutique.sh```


We also provide the load generation script for Figure 8 in the paper for reference.

    
    cd TopFull/TopFull_loadgen
    ./run_fig8_loadgen.sh
    


