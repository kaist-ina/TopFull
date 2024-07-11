"""
Resource Collector module.
Collect CPU utilization for each pods from cadvisor

Import this module and run the below command.
-----------------------------
t = threading.Thread(target=run, args=())
t.start()
-----------------------------

It records CPU utilization periodically at 'cpu_util', which is a global dictionary.
You can get CPU utilization from 'cpu_util'

You can configure observation targets by modifying 'service_list'
"""

import json
import requests
import redis
import timeit
import time
import subprocess
import threading
from datetime import datetime
from json.decoder import JSONDecodeError

# Online Boutique service lists
service_list = ["redis-cart", "frontend", "checkoutservice", "productcatalogservice", "recommendationservice", "shippingservice", "emailservice", "cartservice", "currencyservice"]

# Train Ticket service lists
# service_list = ["ts-assurance-service", "ts-auth-service", "ts-avatar-service", "ts-basic-service",
#                      "ts-cancel-service", "ts-config-service", "ts-consign-price-service",
#                      "ts-consign-service", "ts-contacts-service", "ts-execute-service", "ts-food-map-service",
#                      "ts-food-service", "ts-inside-payment-service", "ts-news-service", "ts-notification-service",
#                      "ts-order-other-service", "ts-order-service", "ts-payment-service",
#                      "ts-preserve-other-service", "ts-preserve-service", "ts-price-service", "ts-rebook-service",
#                      "ts-route-plan-service", "ts-route-service", "ts-seat-service", "ts-security-service",
#                      "ts-station-service", "ts-ticket-office-service", "ts-ticketinfo-service", "ts-train-service",
#                      "ts-travel-plan-service", "ts-travel-service", "ts-travel2-service", "ts-ui-dashboard",
#                      "ts-user-service", "ts-verification-code-service", "ts-voucher-mysql", "ts-voucher-service"]

cpu_util = {}
collect_time = [0]

def exec_command(command):
    p = subprocess.Popen(command, shell=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    out, err = p.communicate()
    ret = p.returncode
    return out, err, ret

def getContainerId3():
    """
    Output: dict[service_name] -> list of container id 
    """
    out, err, ret = exec_command(
        f"kubectl get po -ojson | jq .items"
    )
    obj = json.loads(out)
    result = {}
    for service_name in service_list:
        result[service_name] = []

    for ob in obj:
        try:
            pod_name = ob['metadata']['name']
            pod_name = pod_name.split('-')[:-2]
            pod_name = "-".join(pod_name)
            if pod_name in service_list:
                containers = ob['status']['containerStatuses']
                for container in containers:
                    if 'proxy' in container['name']:
                        continue
                    result[pod_name].append(container['containerID'].split('/')[-1])
        except:
            continue
                
    return result


def getContainerId2(keyword):
    out, err, ret = exec_command(
        f"kubectl get po -ojson | jq .items | jq -c 'map(select(.metadata.name | contains (\"" + keyword + "\")))' | jq -r '.[].status.containerStatuses' | jq -c 'map(select(.name | contains (\"proxy\") | not))' | jq -r '.[0].containerID'")
    out = out.decode('utf-8').strip()
    out = out.split("\n")
    result = []
    for o in out:
        result.append(o.split('/')[-1])

    return result

def timedeltaToSeconds(d1, d2):
    _d1 = d1[:-4]
    _d2 = d2[:-4]

    t1 = datetime.strptime(_d1, "%Y-%m-%dT%H:%M:%S.%f")
    t2 = datetime.strptime(_d2, "%Y-%m-%dT%H:%M:%S.%f")

    return (t2 - t1).total_seconds()

def parseNetworkStats(stats, ret):
    # handle network i/o data
    tmp = {}

    last_idx = len(stats[1]['stats']) - 1
    first_idx = last_idx - 2 

    first = stats[1]['stats'][first_idx]['network']["interfaces"]
    last = stats[1]['stats'][last_idx]['network']["interfaces"]


    first_time = stats[1]['stats'][first_idx]['timestamp']
    last_time = stats[1]['stats'][last_idx]['timestamp']
    time_diff = timedeltaToSeconds(first_time, last_time)

    for entry in last:
        interface_name = entry['name']
        if 'cali' not in interface_name:
            continue

        tmp[interface_name] = {}
        tmp[interface_name]['rx_kb'] = entry['rx_bytes'] / 1024
        tmp[interface_name]['rx_packets'] = entry['rx_packets']
        tmp[interface_name]['rx_errors'] = entry['rx_errors']
        tmp[interface_name]['rx_dropped'] = entry['rx_dropped']
        tmp[interface_name]['tx_kb'] = entry['tx_bytes'] / 1024
        tmp[interface_name]['tx_packets'] = entry['tx_packets']
        tmp[interface_name]['tx_errors'] = entry['tx_errors']
        tmp[interface_name]['tx_dropped'] = entry['tx_dropped']

    for entry in first:
        interface_name = entry['name']
        if 'cali' not in interface_name:
            continue

        if interface_name in tmp.keys():
            tmp[interface_name]['rx_kb'] -= entry['rx_bytes'] / 1024
            tmp[interface_name]['rx_packets'] -= entry['rx_packets']
            tmp[interface_name]['rx_packets'] /= time_diff
            tmp[interface_name]['rx_errors'] -= entry['rx_errors']
            tmp[interface_name]['rx_dropped'] -= entry['rx_dropped']
            tmp[interface_name]['tx_kb'] -= entry['tx_bytes'] / 1024
            tmp[interface_name]['tx_packets'] -= entry['tx_packets']
            tmp[interface_name]['tx_packets'] /= time_diff
            tmp[interface_name]['tx_errors'] -= entry['tx_errors']
            tmp[interface_name]['tx_dropped'] -= entry['tx_dropped']
        else:
            tmp[interface_name] = {}

    out, _, _ = exec_command('ssh -t ' + WORKER_MACHINE + ' route | awk \'{print $1" "$8}\' | grep cali')
    out = out.decode('utf-8').split('\n')
    tmp2 = {}
    for entry in out:
        if not entry.startswith('192'):
            continue
        sp = entry.split(' ')
        if sp[1].split('\r')[0] in tmp.keys():
            tmp2[sp[0]] = tmp[sp[1].split('\r')[0]]

    for entry in ret:
        service_name = entry['name']
        ip = getPodIP(service_name)
        if ip in tmp2.keys():
            entry['network'] = tmp2[ip]

    return ret

def parseMemoryDiskStats(stat, entry, first, last, first_idx, last_idx):
    def getTotalMemory(stat, first_idx, last_idx):
        total_kb = 0
        for idx in range(first_idx, last_idx + 1):
            total_kb += stat[idx]['memory']['usage']
        return total_kb / 1024.0

    def process_diskio(diskio, field):
        """
        Sum up all the disk IO bytes for a given field (Sync, Async, Read, Write).

        Only considering io_service_bytes stats right now (io_serviced is ignored).
        """
        total = 0
        if 'io_service_bytes' in diskio.keys():
            io_stats = diskio['io_service_bytes']
            for entry in io_stats:
                total += entry['stats'][field]

        return total

    entry['memory']['usage'] = getTotalMemory(stat, first_idx, last_idx) / (last_idx - first_idx + 1)
    entry['cache']['usage'] = last['memory']['cache']

    start_async_bytes = process_diskio(first['diskio'], 'Async')
    end_async_bytes = process_diskio(last['diskio'], 'Async')
    start_sync_bytes = process_diskio(first['diskio'], 'Sync')
    end_sync_bytes = process_diskio(last['diskio'], 'Sync')
    start_read_bytes = process_diskio(first['diskio'], 'Read')
    end_read_bytes = process_diskio(last['diskio'], 'Read')
    start_write_bytes = process_diskio(first['diskio'], 'Write')
    end_write_bytes = process_diskio(last['diskio'], 'Write')

    entry['diskio']['async'] = end_async_bytes - start_async_bytes
    entry['diskio']['sync'] = end_sync_bytes - start_sync_bytes
    entry['diskio']['read'] = end_read_bytes - start_read_bytes
    entry['diskio']['write'] = end_write_bytes - start_write_bytes

    return entry

def parseStats(stats):
    # CPU, memory, cache, and disk I/O
    ret = []
    for e in stats[0]:
        if 'aliases' not in e.keys():
            continue

        container_name = e['spec']['labels']['io.kubernetes.container.name']
        pod_name = e['spec']['labels']['io.kubernetes.pod.name']
        if container_name == "POD":
            continue

        entry = {'name': container_name, 'pod_name': pod_name, 'cpu': {}, 'memory': {}, 'network': {}, 'diskio': {},
                 'cache': {}}

        stat = e['stats']
        stat_len = len(stat)
        first_idx = 0  
        last_idx = stat_len - 1

        first = stat[first_idx]
        last = stat[last_idx]

        entry['cpu']['usage'] = last['cpu']['usage']['total'] - first['cpu']['usage']['total']
        entry = parseMemoryDiskStats(stat, entry, first, last, first_idx, last_idx)

        ret.append(entry)

    ret = parseNetworkStats(stats, ret)

    return ret

def parseStats_v2(stats):
    # CPU, memory, cache, and disk I/O
    ret = []
    for service_name, ee in stats.items():
        for e in ee:

            for stat in e.values():
                entry = {'name': service_name, 'cpu': {}, 'memory': {}, 'network': {}, 'diskio': {}, 'cache': {}}

                cnt = 0
                cpu_total = 0
                s = len(stat)-1
                e = len(stat)-1-5 if len(stat)-1-5 >= -1 else -1
                for idx in range(s, e, -1):
                    if 'cpu_inst' in stat[idx].keys():
                        cpu_total += stat[idx]['cpu_inst']['usage']['total']
                        cnt += 1

                if cnt == 0:
                    print("No CPU metric collected. It won't update the value in the Redis server.")
                    continue
                else:
                    entry['cpu'] = (cpu_total / cnt) / 1000000 # in milli-core

                stat_len = len(stat)
                first_idx = 0 
                last_idx = stat_len - 1

                first = stat[first_idx]
                last = stat[last_idx]
                entry = parseMemoryDiskStats(stat, entry, first, last, first_idx, last_idx)

                ret.append(entry)

    return ret


def parseStats_v3(stats):
    # CPU, memory, cache, and disk I/O
    ret = []
    for service_name, e in stats[0].items():

        for stat in e.values():
            entry = {'name': service_name, 'cpu': {}, 'memory': {}, 'network': {}, 'diskio': {}, 'cache': {}}

            entry['cpu'] = stats[2][service_name] * 1000

            stat_len = len(stat)
            first_idx = 0
            last_idx = stat_len - 1

            first = stat[first_idx]
            last = stat[last_idx]
            entry = parseMemoryDiskStats(stat, entry, first, last, first_idx, last_idx)

            ret.append(entry)

    ret = parseNetworkStats(stats, ret)

    return ret


def getStats(port=8080):
    def getcAdvisorIP():
        out, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[0].status.podIP}\'')
        return out.decode('utf-8')

    ipAddr = getcAdvisorIP()
    url = 'http://{}:{}/api/v1.3/subcontainers'.format(ipAddr, port)
    resp = requests.get(url)
    ret1 = json.loads(resp.content.decode('utf-8'))

    url = 'http://{}:{}/api/v1.3/containers'.format(ipAddr, port)
    resp = requests.get(url)
    ret2 = json.loads(resp.content.decode('utf-8'))

    return ret1, ret2

def getStats_v2(port=8080):
    def getcAdvisorIP():
        out, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[0].status.podIP}\'')
        return out.decode('utf-8')

    def getDockerID():
        ret = {}
        for service_name in service_list:
            containerID = getContainerId2(service_name)
            ret[service_name] = containerID
        return ret

    ret1 = {}
    dockerID = getDockerID()
    ipAddr = getcAdvisorIP()
    print("Start quering")
    for service_name, containerID in dockerID.items():
        print(f"Query {service_name}")

        for id in containerID:
            url = 'http://{}:{}/api/v2.0/stats/{}?type=docker'.format(ipAddr, port, id)
            resp = requests.get(url)
            resp = resp.content.decode('utf-8')
            try:
                j = json.loads(resp)
                if service_name in ret1:
                    ret1[service_name].append(j)
                else:
                    ret1[service_name] = [j]
            except JSONDecodeError:
                print('JSONDecodeError occurred.')
                print(resp)

    return ret1


def getStats_v3(port=8080):
    def getcAdvisorIP():
        out, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[0].status.podIP}\'')
        return out.decode('utf-8')

    def getDockerID():
        ret = {}
        for service_name in service_list:
            containerID = getContainerId2(service_name)
            ret[service_name] = containerID
        return ret

    ret1 = {}
    print("Start docker id query")
    dockerID = getDockerID()
    ipAddr = getcAdvisorIP()
    print("Start quering")
    tids = []

    for service_name, containerID in dockerID.items():

        for id in containerID:
            url = 'http://{}:{}/api/v2.0/summary/{}?type=docker'.format(ipAddr, port, id)
            resp = requests.get(url)
            resp = resp.content.decode('utf-8')
            try:
                j = json.loads(resp)
                cpu = list(j.values())[0]['latest_usage']['cpu']
                if service_name in ret1:
                    ret1[service_name].append(cpu)
                else:
                    ret1[service_name] = [cpu]

            except JSONDecodeError:
                print('JSONDecodeError occurred.')
                print(resp)
    for tid in tids:
        tid.join()
    
    print(ret1)
    for service_name, cpus in ret1.items():
        cpu_total = 0
        for cpu in cpus:
            cpu_total += cpu
        cpu_total /= len(cpus)
        ret1[service_name] = cpu_total
    print(ret1)


def getStats_container(containerID, idx, ret, ipAddr, port):
    url = 'http://{}:{}/api/v2.0/summary/{}?type=docker'.format(ipAddr, port, containerID)
    resp = requests.get(url)
    resp = resp.content.decode('utf-8')
    try:
        j = json.loads(resp)
        cpu = list(j.values())[0]['latest_usage']['cpu']
        ret[idx] = cpu

    except JSONDecodeError:
        print('JSONDecodeError occurred.')

def getStats_thread(service_name, ipAddr, port, ret, container_ids):
    ret[service_name] = [0 for i in range(len(container_ids))]
    tids = []
    for i, id in enumerate(container_ids):
        tid = threading.Thread(target=getStats_container, args=(id, i, ret[service_name], ipAddr, port))
        tids.append(tid)
        tid.start()
    for tid in tids:
        tid.join()

    return

def getStats_container_two(containerID, idx, ret, ipAddrs, port):
    for ipAddr in ipAddrs:
        url = 'http://{}:{}/api/v2.0/summary/{}?type=docker'.format(ipAddr, port, containerID)
        resp = requests.get(url)
        resp = resp.content.decode('utf-8')
        try:
            j = json.loads(resp)
            cpu = list(j.values())[0]['latest_usage']['cpu']
            ret[idx] = cpu

        except JSONDecodeError:
            continue
            

def getStats_thread_two(service_name, ipAddrs, port, ret, container_ids):
    ret[service_name] = [-1 for i in range(len(container_ids))]
    tids = []
    for i, id in enumerate(container_ids):
        tid = threading.Thread(target=getStats_container_two, args=(id, i, ret[service_name], ipAddrs, port))
        tids.append(tid)
        tid.start()
    for tid in tids:
        tid.join()

    return

def getStats_v4_two(port=8080):
    def getcAdvisorIP():
        # Below number of lines should match the number of kubernetes worker machines (nodes)
        out1, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[0].status.podIP}\'')
        out2, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[1].status.podIP}\'')
        out3, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[2].status.podIP}\'')
        out4, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[3].status.podIP}\'')
        out5, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[4].status.podIP}\'')

        return [out1.decode('utf-8'), out2.decode('utf-8'), out3.decode('utf-8'), out4.decode('utf-8'), out5.decode('utf-8')]
    
    container_ids = getContainerId3()

    ret1 = {}
    for service_name in service_list:
        ret1[service_name] = []

    ipAddrs = getcAdvisorIP()
    tids = []

    for service_name in service_list:
        tid = threading.Thread(target=getStats_thread_two, args=(service_name, ipAddrs, port, ret1, container_ids[service_name]))
        tids.append(tid)
        tid.start()

    for tid in tids:
        tid.join()

    for service_name, cpus in ret1.items():
        cpu_total = 0
        length = 0
        for cpu in cpus:
            if cpu <= 2:
                continue
            cpu_total += cpu
            length += 1
        if length == 0:
            cpu_total = 0
        else:
            cpu_total /= length
        ret1[service_name] = cpu_total
    return ret1

def run(event):
    for service_name in service_list:
        cpu_util[service_name] = 0
    while True:
        if event.is_set():
            return
        start = timeit.default_timer()
        result = getStats_v4_two()
        end = timeit.default_timer()
        for key, value in result.items():
            cpu_util[key] = value
        collect_time[0] = end - start

def getStats_v4(port=8080):
    def getcAdvisorIP():
        out1, err, ret = exec_command('kubectl get pod -n cadvisor -ojsonpath=\'{.items[0].status.podIP}\'')
        return out1.decode('utf-8')
    
    container_ids = getContainerId3()
    ret1 = {}
    for service_name in service_list:
        ret1[service_name] = []

    ipAddr = getcAdvisorIP()

    tids = []

    # for service_name, containerID in dockerID.items():
    for service_name in service_list:
        tid = threading.Thread(target=getStats_thread, args=(service_name, ipAddr, port, ret1, container_ids[service_name]))
        tids.append(tid)
        tid.start()

    for tid in tids:
        tid.join()
    
    for service_name, cpus in ret1.items():
        cpu_total = 0
        for cpu in cpus:
            cpu_total += cpu
        cpu_total /= len(cpus)
        ret1[service_name] = cpu_total
    return ret1



if __name__ == '__main__':
    while True:
        start = timeit.default_timer()
        print(getStats_v4_two())
        end = timeit.default_timer()
