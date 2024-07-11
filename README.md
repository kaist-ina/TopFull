# TopFull (SIGCOMM 2024)

This is an official Github repository for the SIGCOMM '24 paper "TopFull: An Adaptive Top-Down Overload Control for SLO-Oriented Microservices".
The repository includes our implementation of TopFull on microservices environment.


## How to run experiments

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

## Setting up Kubernetes environment (master nodes and worker nodes)

## Setting up load generation node

## Setting up configurations
