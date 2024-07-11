# TopFull (SIGCOMM 2024)

This is an official Github repository for the SIGCOMM '24 paper "TopFull: An Adaptive Top-Down Overload Control for SLO-Oriented Microservices".
The repository includes our implementation of TopFull on microservices environment.


## How to run experiments with TopFull

Once all the environments are set up with a microservices application running on Kubernetes, overload experiments are carried out by executing codes in the dedicated order.

1. Starting load controller at master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src/proxy
    go run proxy_online_boutique.go
    ```

2. Running TopFull system (RL ver) at master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src
    python deploy_rl.py
    ```
    You may run python deploy_mimd.py for TopFull with MIMD heuristic instead of RL.

3. Generate APIs workloads at load generation node.
    ```
    cd TopFull/TopFull_loadgen
    ./online_boutique_create.sh
    ./online_boutique_create2.sh
    ```

4. Monitor and record results at master node.
    ```
    cd TopFull/TopFull_master
    python metric_collector.py
    ```

## How to run experiments with Breakwater and DAGOR

In master node, instead of online_boutique_original_custom.yaml,
execute online_boutique_breakwater_custom.yaml and online_boutique_dagor_custom.yaml.
Their overload control algorithms are implemented in the online boutique application.

1. Starting load controller at master node.
    ```
    cd TopFull/TopFull_master/online_boutique_scripts/src/proxy
    go run proxy_online_boutique.go
    ```

2. Generate APIs workloads at load generation node.
    ```
    cd TopFull/TopFull_loadgen
    ./online_boutique_create.sh
    ./online_boutique_create2.sh
    ```

3. Monitor and record results at master node.
    ```
    cd TopFull/TopFull_master
    python metric_collector.py
    ```

## Setting up Kubernetes environment (master nodes and worker nodes)

1. Install cri-docker & environment setup (Master & Worker)

```bash
sudo swapoff -a

curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable --now docker && sudo systemctl status docker --no-pager
sudo usermod -aG docker worker
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
echo "deb [signed-by=/usr/share/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee /etc/apt/sources.list.d/kubernetes.list

# It acknowledge packages after the update
sudo apt-get update

# Install k8s
sudo apt-get install -y kubelet='1.26.0-00' kubeadm='1.26.0-00' kubectl='1.26.0-00'

# Check version
kubectl version --short

# Fix version
sudo apt-mark hold kubelet kubeadm kubectl
```

3. Cluster Init

```bash
sudo kubeadm init --pod-network-cidr 192.168.0.0/16 --service-cidr 10.96.0.0/12 --cri-socket unix://var/run/cri-dockerd.sock
```

4. CNI installation

```bash
curl https://docs.projectcalico.org/manifests/calico.yaml -O

# Important!
# Set VXLAN mode
kind: DaemonSet
- name: CALICO_IPV4POOL_IPIP
  value: "Never"
- name: CALICO_IPV4POOL_VXLAN
  value: "Always"

kubectl apply -f calico.yaml
```


5. cAdvisor

```python
# https://github.com/google/cadvisor/tree/master/deploy/kubernetes

$ kubectl kustomize deploy/kubernetes/base | kubectl apply -f -
```

6. Connecting worker nodes 
at master node
```bash
sudo kubeadm token create --print-join-command
```
at worker node
```bash
sudo kubeadm join "token" --cri-socket unix://var/run/cri-dockerd.sock
```
7. Setting up microservices application images (online boutique)
To build online boutique microservices follow the below.
```bash
cd TopFull/online_boutique_source_code/microservices-demo-custom
./build_all.sh
cd TopFull/online_boutique_source_code/microservices-demo-breakwater
./build_all.sh
cd TopFull/online_boutique_source_code/microservices-demo-dagor-custom
./build_all.sh
```

8. Running microservices applications (online boutique)
```bash
cd TopFull/TopFull_master/online_boutique_scripts/deployments
kubectl apply -f online_boutique_original_custom.yaml
kubectl apply -f metric-server-latest.yaml
```


## Setting up master node and application images
We run TopFull algorithm that makes load control decisions at the master node. Install the required packages for running the codes. They are provided in requirements.txt file.


## Setting up load generation node
Load is generated through locust. Install the required packages for running the code. They are provided as requirements.txt file.
A single locust process cannot use multiple CPU cores. Therefore, multiple processes should be created to generate more users. We provide bash files for such use cases.

## Setting up configurations
    ```
    TopFull/TopFull_master/online_boutique_scripts/src/global_config.json
    ```
