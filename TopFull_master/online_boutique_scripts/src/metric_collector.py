# Collect latency and goodput from locust by using REST api

import requests
import time
import csv
import os

import json
global_config_path = "/home/topfull-master/TopFull/TopFull_master/online_boutique_scripts/src/global_config.json"
with open(global_config_path, "r") as f:
    global_config = json.load(f)

class Collector:
    def __init__(self, hostname="http://honey3.kaist.ac.kr:8089/stats/requests", code="online_boutique"):
        self.hostname = hostname
        if code == "online_boutique":
            self.code = [
                ("GET", "getcart", 8888),
                ("GET", "getproduct", 8888),
                ("POST", "postcart", 8888),
                ("POST", "postcheckout", 8889),
                ("POST", "emptycart", 8888)
            ]
        elif code == "train_ticket":
            self.code = [
                ("POST", "high_speed_ticket", 8089),
                ("POST", "normal_speed_ticket", 8090),
                ("POST", "query_cheapest", 8089),
                ("POST", "query_min_station", 8089),
                ("POST", "query_quickest", 8089),
                ("POST", "query_order", 8089),
                ("POST", "query_order_other", 8090),
                ("GET", "query_route", 8089),
                ("GET", "query_food", 8089),
                ("GET", "enter_station", 8089),
                ("POST", "preserve_normal", 8089),
                ("GET", "query_contact", 8090),
                ("POST", "query_payment", 8090)
            ]
        else:
            self.code = code

    def query(self, port=8888):
        """
        Query metrics
        Input: api_code
        Output: metrics of api
        """
        # ports = [8888]
        # ports = [8888, 8889, 8899]
        ports = global_config["locust_port"]
        ports = [i+8888 for i in range(ports)]
        result = {}
        for port in ports:
            try:
                response = requests.get(global_config["locust_url"] + ":" + str(port))
            except:
                continue
            data = response.text
            data = data.split("/")[:-1]
            for i in range(len(self.code)):
                elem = data[i]
                tmp = elem.split("=")

                name = tmp[0]
                rps = tmp[1]
                fail = tmp[2]
                latency95 = tmp[3]
                latency99 = tmp[4]
                if name in result:
                    result[name][0] += float(rps)
                    result[name][1] += float(fail)
                    result[name][2] = max(result[name][2], float(latency95))
                    result[name][3] = max(result[name][3], float(latency99))
                else:
                    result[name] = [float(rps), float(fail), float(latency95), float(latency99)]
        for name in list(result.keys()):
            result[name] = (result[name][0], result[name][1], result[name][2])
            # result[name] = (result[name][0], result[name][1], result[name][2], result[name][3])
        return result

    
    def query_latency(self, api):
        response = requests.get(f"http://honey3.kaist.ac.kr:8089/stats/requests")
        data = response.json()
        stats = data["stats"]

        method, path, _ = self.code[api]
        for stat in stats:
            if method == stat["method"] and path in stat["name"]:
                return data['current_response_time_percentile_95']


def record_train_ticket():
    collector = Collector(code="train_ticket")
    apis = [i[1] for i in collector.code]
    log_path = "/home/master_artifact/train-ticket/src/logs/"
    proxies = {
        'http': 'http://egg3.kaist.ac.kr:8090'
    }
    url = "http://egg3.kaist.ac.kr:8090/thresholds"

    # Init
    if os.path.exists(log_path+"goodput.csv"):
        os.remove(log_path+"goodput.csv")
    if os.path.exists(log_path+"threshold.csv"):
        os.remove(log_path+"threshold.csv")
    
    with open(log_path+"goodput.csv", "a") as f1:
        with open(log_path+"threshold.csv", "a") as f2:
                w1 = csv.writer(f1)
                w2 = csv.writer(f2)
                w1.writerow(apis)
                w2.writerow(apis)

    # while True:
    for i in range(500):
        time.sleep(2)
        # Record goodput
        goodputs = []
        for i, api in enumerate(apis):
            metric, _ = collector.query(i)
            goodput = metric['current_rps'] - metric['current_fail_per_sec']
            goodputs.append(goodput)

        # Record threshold
        thresholds = []
        response = requests.get(url, proxies=proxies)
        if not response.ok:
            continue
        body = response.text
        body = body.split("/")[:-1]
        for elem in body:
            elem = elem.split("=")
            thresholds.append(float(elem[1]))
        
        # Write csv
        with open(log_path+"goodput.csv", "a") as f1:
            with open(log_path+"threshold.csv", "a") as f2:
                w1 = csv.writer(f1)
                w2 = csv.writer(f2)

                w1.writerow(goodputs)
                w2.writerow(thresholds)

            
def record_online_boutique():
    c = Collector(code=global_config["microservice_code"])
    apis = global_config["record_target"]
    log_path = global_config["record_path"]

    # Init
    for api in apis:
        filename = log_path + api + ".csv"
        if os.path.exists(filename):
            os.remove(filename)

        with open(filename, "a") as f:
            w = csv.writer(f)
            w.writerow(["RPS", "Fail", "Goodput", "Latency95", "Latency99"])
    
    filename = log_path + "total.csv"
    if os.path.exists(filename):
        os.remove(filename)
    with open(filename, "a") as f:
        w = csv.writer(f)
        w.writerow(["RPS", "Fail", "Goodput", "Latency95", "Latency99"])


    while True:
        time.sleep(1)
        metric = c.query()
        total_goodput = {}
        total_rps = 0
        total_fail = 0
        total_latency95 = 0
        total_latency99 = 0

        for i, api in enumerate(apis):
            # rps, fail, latency95, latency99 = metric[api]
            rps, fail, latency95 = metric[api]
            latency99 = 0
            total_rps += rps
            total_fail += fail
            total_latency95 += latency95
            total_latency99 += latency99
            with open(log_path + api + ".csv", "a") as f:
                w = csv.writer(f)
                w.writerow([rps, fail, rps-fail, latency95, latency99])
                total_goodput[api] = rps-fail
        with open(log_path + "total.csv", "a") as f:
            w = csv.writer(f)
            w.writerow([total_rps, total_fail, total_rps-total_fail, total_latency95/len(apis), total_latency99/len(apis)])
        out = ""
        for api in apis:
            out += f"{api}={total_goodput[api]}   "
        print(out)


import csv
if __name__ == "__main__":
    record_online_boutique()
