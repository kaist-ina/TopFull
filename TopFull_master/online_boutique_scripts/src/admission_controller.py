import signal
import os
import subprocess
import time
import json
import csv
import requests
import threading

from kubernetes import client, config
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def send_signal(pods):
    for pod in pods:
        command = "kubectl exec {} -- kill -USR1 1".format(pod)
        subprocess.call(command, shell=True)
        print("Send signal to pod " + pod)

def send_signal_one(pods):
    command = "kubectl exec {} -- kill -USR1 1".format(pods)
    subprocess.call(command, shell=True)

def browse_pods(v1):
    ret = v1.list_namespaced_pod("default")
    pods = []
    frontend = []
    valid_pods = ["checkoutservice", "productcatalogservice", "recommendationservice", "shippingservice", "emailservice"]
    for pod in ret.items:
        name = pod.metadata.name
        deploy = name.split("-")[0]
        if deploy in valid_pods:
            pods.append(name)
        elif deploy == "frontend":
            frontend.append(pod.status.pod_ip)
    return pods, frontend


def write_remote(url, filename, data):
    cmd = ["ssh", url, "sudo tee {}".format(filename)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    p.communicate(data)
    return


def get_histogram(frontend_ips):
    ret = [0 for i in range(896)]
    for ip in frontend_ips:
        res = requests.get("http://{}:8080/api/v1/histogram".format(ip))
        if res.status_code != 200:
            continue
        result = res.json()
        for i in range(896):
            ret[i] += result[i]
    for i in range(896):
        ret[i] = str(ret[i])
    return ret

class kubeAPI:
    def __init__(self):
        config.load_kube_config()
        self.v1 = client.CoreV1Api()
        self.api = client.CustomObjectsApi()
    def browse_pods(self):
        ret = self.v1.list_namespaced_pod("default")
        pods = []
        frontend = []
        valid_pods = ["checkoutservice", "productcatalogservice", "recommendationservice", "shippingservice", "emailservice"]
        for pod in ret.items:
            name = pod.metadata.name
            deploy = name.split("-")[0]
            if deploy in valid_pods:
                pods.append(name)
            elif deploy == "frontend":
                frontend.append(pod.status.pod_ip)
        return pods, frontend
    
    def browse_pods_one(self):
        ret = self.v1.list_namespaced_pod("default")
        pods = []
        valid_pods = ["checkoutservice", "productcatalogservice", "recommendationservice", "shippingservice", "emailservice"]
        for pod in ret.items:
            name = pod.metadata.name
            deploy = name.split("-")[0]
            if deploy in valid_pods:
                pods.append(name)
                valid_pods.remove(deploy)
        return pods

    def send_signal(self, pods, num):
        for pod in pods:
            if num == 1:
                command = "kubectl exec {} -- kill -USR1 1".format(pod)
            elif num == 2:
                command = "kubectl exec {} -- kill -USR2 1".format(pod)

            subprocess.call(command, shell=True)
            print(f"Send signal {num} to pod " + pod)

    def get_metrics(self, targets, cpu_scale=1000000, mem_scale=1024):
        # api = client.CustomObjectsApi()
        resource = self.api.list_namespaced_custom_object(group="metrics.k8s.io",version="v1beta1", namespace="default", plural="pods")
        result = {}
        for pod in resource['items']:
            try:
                deploy = pod['metadata']['labels']['app']
                if deploy in targets:
                    cpu = 0
                    memory = 0
                    print(pod)
                    for container in pod['containers']:
                        cpu += int(container['usage']['cpu'][:-1]) // cpu_scale
                        memory += int(container['usage']['memory'][:-2]) // mem_scale
                    if deploy in result:
                        result[deploy]['cpu'] += cpu
                        result[deploy]['memory'] += memory
                    else:
                        result[deploy] = {'cpu': cpu, 'memory': memory}

            except:
                continue
        return result
    
    def get_deployment_replicas(self, target, namespace='default'):
        ret = self.v1.list_namespaced_pod(namespace)
        result = 0
        for pod in ret.items:
            name = pod.metadata.name
            deploy = name.split("-")[0]
            if deploy == target:
                result += 1
        return result



if __name__ == "__main__":
    kube = kubeAPI()
    kube.get_metrics(['productcatalogservice', 'checkoutservice'])