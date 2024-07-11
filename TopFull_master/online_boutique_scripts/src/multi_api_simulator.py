from platform import node
from sre_parse import State
from statistics import mean
from sys import api_version
import numpy as np
import os
from collections import OrderedDict as OD
import itertools
import json
import random
import scipy.stats as st


class Node:
    # pivot capacity where latency starts to increase if workload exceeds the pivot capacity
    # min latency is average latency when workload is below pivot capacity
    # var latency is variance to calculate 95%-tile latency assuming latency follows normal distribution
    # pattern is workload latency characteristics, rather avg latency increase exponential or linear
    def __init__(self, pivotcapacity, minlatency, varlatency, powcoeff = 1.5):
        self.pivotcapacity = pivotcapacity
        self.minlatency = minlatency
        self.varlatency = varlatency
        self.powcoeff = powcoeff

    def charLatency(self, workload):
        if workload < self.pivotcapacity:
            avglatency = self.minlatency
            varlatency = self.varlatency
        else:
            avglatency = self.minlatency * pow(self.powcoeff, (workload - self.pivotcapacity)/self.pivotcapacity)
            varlatency = self.varlatency * (avglatency/self.minlatency)
        return avglatency, varlatency

    def overload(self, workload):
        if workload < self.pivotcapacity:
            return False
        else:
            return True


class API:
    # path lists of serial paths, where lists can be parallel
    def __init__(self, paths):
        self.paths = paths

    def e2eLatencyChar(self, workload):
        maxavg = 0
        maxvar = 0
        for path in self.paths:
            average = 0
            variance = 0
            #avg latency for path
            for node in path:
                avg, var = node.charLatency(workload)
                average += avg
                variance += var
            maxavg = max(maxavg, average)
            maxvar = max(maxvar, variance)
        return maxavg, maxvar
    
    def e2eGoodputLatency(self, workload):
        avg, var = self.e2eLatencyChar(workload)
        lat100 = 0
        lat95 = 0
        avgLat = 0
        for _ in range (20):
            tmpLat = np.random.normal(avg, var)
            tmpLat = max(0, tmpLat)
            avgLat += tmpLat/20
            if tmpLat > lat100:
                lat95 = lat100
                lat100 = tmpLat
            elif tmpLat > lat95:
                lat95 = tmpLat

        # z = (x-avg)/var where x is datapoint
        samplevar = (lat95-avgLat)/1.645
        z = (1000-avgLat)/samplevar
        goodput = workload * st.norm.cdf(z)

        return goodput, lat95


def generate_random_node():
    return Node(
        random.uniform(50, 500), 
        random.uniform(100, 500), 
        random.uniform(2, 10), 
        random.uniform(1.5, 3)
    )

def generate_dag_paths(num_nodes, num_edges):
    nodes = [generate_random_node() for _ in range(num_nodes)]
    edges = []

    def add_edge(src, dest):
        if src != dest and [src, dest] not in edges:
            edges.append([src, dest])

    for _ in range(num_edges):
        while True:
            src_idx = random.randint(0, num_nodes - 1)
            dest_idx = random.randint(0, num_nodes - 1)
            if src_idx != dest_idx:
                src = nodes[src_idx]
                dest = nodes[dest_idx]
                parents = set()
                stack = [src_idx]
                while stack:
                    node_idx = stack.pop()
                    if node_idx == dest_idx:
                        break
                    for edge in edges:
                        if edge[1] == nodes[node_idx] and nodes.index(edge[0]) not in parents:
                            parents.add(nodes.index(edge[0]))
                            stack.append(nodes.index(edge[0]))
                else:
                    add_edge(src, dest)
                    break

    return edges

def dags_random():
    api_paths = []
    for _ in range(random.randint(1, 3)):
        num_nodes = random.randint(1, 5)
        max_edges = num_nodes * (num_nodes - 1) // 2  # Maximum possible edges in a DAG
        num_edges = random.randint(1, max_edges) if max_edges > 0 else 0
        api_paths.append(generate_dag_paths(num_nodes, num_edges))

    return tuple(api_paths)




# Scenario of single api with single node simulation
def single_node_example():
    node = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    api_path = [[node]]
    return api_path

# Scenario of single api with 2 serial node 1 parallel node execution path
def single_api_topology():
    node1 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node2 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node3 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    api_path = [[node1, node2],[node3]]
    return api_path

# 2 api random
def two_api_topology():
    node1 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node2 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node3 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    api_path1 = [[node1, node2],[node1, node3]]
    api_path2 = [[node1, node2]]
    return api_path1, api_path2

def three_api_topology1():
    node1 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node2 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node3 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node4 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    api_path1 = [[node1, node2]]
    api_path2 = [[node2, node3]]
    api_path3 = [[node3, node4]]
    return api_path1, api_path2, api_path3

def three_api_topology2():
    node1 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node2 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    node3 = Node(random.uniform(50,500), random.uniform(100,500), random.uniform(2,10), random.uniform(1.5,3))
    api_path1 = [[node1]]
    api_path2 = [[node1, node2]]
    api_path3 = [[node1, node3]]
    return api_path1, api_path2, api_path3



class Simulator:
    # initial latency
    # initial incoming goodput
    # initial threshold
    # maximal possible goodput (visible only to the simulator)
    def __init__(self):
        self.latency = random.uniform(150, 5000)
        initthres = random.uniform(0.8, 1.2)
        self.targetGoodput = random.uniform(50, 500)
        self.thresGoodput = self.targetGoodput * initthres
        # self.currGoodput = min(self.thresGoodput, self.targetGoodput*(1-(self.thresGoodput-self.targetGoodput)/self.thresGoodput))
        # self.node1 = Node(200, 100, 5, 1.5)
        # self.node2 = Node(200, 100, 4, 2)
        # self.api1 = API([[self.node1, self.node2]])
        self.api1 = API(single_node_example())
    

    def simGoodputLatency(self, action):
        self.thresGoodput = self.thresGoodput*(1+float(action))
        goodput, latency = self.api1.e2eGoodputLatency(self.thresGoodput)
        latency = min(latency, 40000)
        return goodput, latency

    def simGoodput(self, action):
        self.thresGoodput = (1+float(action)) * self.thresGoodput
        goodput = self.expGoodput(self.targetGoodput, self.thresGoodput)
        
        return goodput

    def expGoodput(self, target, thres):
        if thres <= target:
            return thres + self.noise()
        else:
            return target * max(0, (1 - (thres-target)/target)) + self.noise() 

    ### based on the threshold it took goodput will converge to certain value
    ### converging variance should also be random variable
    def nextGoodput(self, target, thres, curr):
        if thres <= target:
            next = thres
        else:
            conv = target * max(0, (1-(thres-target)/target))
            if curr > conv:
                next = (conv + curr) / 2
            else:
                next = conv
        self.currGoodput = next + self.noise()
        return self.currGoodput

    def noise(self, mean=0, std=1):
        noise = random.normalvariate(mean, std)
        return noise

    def noiseLatency(self, mean=0, std=5):
        noiseLatency = random.normalvariate(mean, std)
        return noiseLatency

    def initGraph(self, num_nodes):
        node = Node()
        node.currGoodput
        return node