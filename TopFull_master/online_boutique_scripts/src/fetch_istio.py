import json
import os
import requests
import time
from admission_controller import kubeAPI

onlineBoutiqueFilePath = {
    'checkoutservice': '/home/master_artifact/TopFull/histogram/checkout/queue_delay.csv',
    'productcatalogservice': '/home/master_artifact/TopFull/histogram/product/queue_delay.csv',
    'emailservice': '/home/master_artifact/TopFull/histogram/email/queue_delay.csv',
    'recommendationservice': '/home/master_artifact/TopFull/histogram/recommend/queue_delay.csv',
}


def fetch(address):
    """
    http://egg3.kaist.ac.kr:20001/kiali/api/namespaces/graph?duration=60s&graphType=versionedApp&includeIdleEdges=false&injectServiceNodes=false&boxBy=cluster,namespace,app&throughputType=request&responseTime=95&appenders=deadNode,istio,serviceEntry,sidecarsCheck,workloadEntry,health,throughput,responseTime&rateGrpc=requests&rateHttp=requests&rateTcp=sent&namespaces=default
    """
    addr = address + "/kiali/api/namespaces/graph?duration=60s&graphType=versionedApp&includeIdleEdges=false&injectServiceNodes=false&boxBy=cluster,namespace,app&throughputType=request&responseTime=avg&appenders=deadNode,istio,serviceEntry,sidecarsCheck,workloadEntry,health,throughput,responseTime&rateGrpc=requests&rateHttp=requests&rateTcp=sent&namespaces=default"
    response = requests.get(addr)
    if response.status_code != 200:
        return None
    else:
        return response.json()

class Edge:
    def __init__(self, source, target, rps, latency):
        self.rps = float(rps)
        self.latency = float(latency)
        self.source = source
        self.target = target

"""
Adjacency Matrix of Graph
"""
class Graph:
    def __init__(self, nodes):
        """
        nodes: dictionary of 'id : service name'
        """
        self.matrix = [[None for i in nodes] for j in nodes]
        self.service_name = nodes
        self.service_id = {y: x for x, y in nodes.items()}
        self.matcher = {}
        for i, id in enumerate(nodes.keys()):
            self.matcher[id] = i

    def get_edge(self, source_id, target_id):
        """
        Get edge
        """
        try:
            return self.matrix[self.matcher[source_id]][self.matcher[target_id]]
        except:
            return None
    
    def out_edge(self, node, use_name=False):
        """
        Get outgoing edges of the node
        """
        if use_name:
            id = self.translate_name(node)
        else:
            id = node
        
        result = []
        for edge in self.matrix[self.matcher[id]]:
            if edge != None:
                result.append(edge)
        return result        

    def in_edge(self, node, use_name=False):
        """
        Get incoming edges of the node
        """
        if use_name:
            id = self.translate_name(node)
        else:
            id = node
        
        result = []
        for row in self.matrix:
            if row[self.matcher[id]] != None:
                result.append(row[self.matcher[id]])
        return result

    def get_nodes(self):
        """
        Get all nodes of the graph
        """
        return list(self.service_id.keys())

    def add(self, source_id, target_id, rps, latency):
        """
        Add edge
        """
        edge = Edge(source_id, target_id, rps, latency)
        try:
            self.matrix[self.matcher[source_id]][self.matcher[target_id]] = edge
            return
        except:
            return

    def translate_id(self, id):
        """
        Convert node_id to node_name
        """
        if id in self.service_name:
            return self.service_name[id]
        else:
            return None
            
    def translate_name(self, name):
        """
        Convert node_name to node_id
        """
        if name in self.service_id:
            return self.service_id[name]
        else:
            return None
    
    def print_graph(self):
        nodes_name = self.get_nodes()
        for node_name in nodes_name:
            out_edges = self.out_edge(node_name, use_name=True)
            if len(out_edges) == 0:
                continue
            out = f'{node_name}: '
            for edge in out_edges:
                out += f"{self.translate_id(edge.target)} "
            print(out)

    def print_activate_nodes(self):
        nodes_name = self.get_nodes()
        out = []
        for node_name in nodes_name:
            out_edges = self.out_edge(node_name, use_name=True)
            if len(out_edges) == 0:
                continue
            for edge in out_edges:
                out.append(self.translate_id(edge.target))
        print(list(set(out)))



def construct_dag(data):
    """
    Generate DAG of microservice with rps and latency
    data: result of istio GET request
    """
    nodes = data['elements']['nodes']
    edges = data['elements']['edges']

    service_ids = {} # key: service name, value: id
    for node in nodes:
        try:
            service_ids[node['data']['id']] = node['data']['app']
        except:
            continue
    
    graph = Graph(service_ids)
    for edge in edges:
        try:
            if edge['data']['traffic']['protocol'] == 'grpc':
                graph.add(edge['data']['source'], edge['data']['target'], edge['data']['traffic']['rates']['grpc'], edge['data']['responseTime'])
            elif edge['data']['traffic']['protocol'] == 'http':
                graph.add(edge['data']['source'], edge['data']['target'], edge['data']['traffic']['rates']['http'], edge['data']['responseTime'])
        except:
            continue
    return graph

def processing_time(graph, nodes, use_name=True):
    """
    Get processing time for each services
    time: dict{service name: total time}
    processing time = RT of upstream service - RT of all downstream services
    """
    result = {}
    for node in nodes:
        out_edge = graph.out_edge(node, use_name)
        in_edge = graph.in_edge(node, use_name)
        if len(in_edge) == 0:
            continue
        upstream_latency = 0
        for edge in in_edge:
            upstream_latency += edge.latency
        upstream_latency /= len(in_edge)

        processing_time = upstream_latency
        for edge in out_edge:
            processing_time -= edge.latency
        
        result[node] = processing_time

    return result



def get_processing_time(kind):
    """
    Get total time of each services
    return: dict{service name: total time}
    """
    if kind == "online_boutique":
        global onlineBoutiqueFilePath
        target = onlineBoutiqueFilePath
    result = {}
    for service in list(target.keys()):
        filepath = target[service]
        # Read last line
        with open(filepath, "rb") as f:
            try:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
            except OSError:
                f.seek(0)
                return None
            delay = f.readline().decode()

    return [100 for i in range(5)]


def collect_window(iteration, duration, verbose=False):
    """
    Collect processing time, CPU, memory.
    Take an average of 'iteration' with 'duration' interval
    """
    kube = kubeAPI()
    result = {}

    for i in range(iteration):
        time.sleep(duration)
        data = fetch("http://egg3.kaist.ac.kr:20001")
        graph = construct_dag(data)
        total_time = processing_time(graph, graph.get_nodes())
        resource = kube.get_metrics(list(total_time.keys()))
        for key in list(total_time.keys()):
            if key in resource:
                resource[key]['time'] = total_time[key]
        
        for key in list(resource.keys()):
            if key in result:
                result[key]['cpu'] += resource[key]['cpu']
                result[key]['memory'] += resource[key]['memory']
                result[key]['time'] += resource[key]['time']
            else:
                result[key] = {}
                result[key]['cpu'] = resource[key]['cpu']
                result[key]['memory'] = resource[key]['memory']
                result[key]['time'] = resource[key]['time']
    
    for key in list(result.keys()):
        replicas = kube.get_deployment_replicas(key)
        result[key]['cpu'] /= iteration
        result[key]['cpu'] /= replicas
        result[key]['memory'] /= iteration
        result[key]['memory'] /= replicas
        result[key]['time'] /= iteration

    return result


def main():
    data = fetch("http://egg3.kaist.ac.kr:20001")
    graph = construct_dag(data)
    graph.print_activate_nodes()


if __name__ == "__main__":
    main()