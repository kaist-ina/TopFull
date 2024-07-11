#!/usr/bin/python
#
# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import random
from locust import HttpLocust, TaskSet, between, task, events, constant_throughput, constant_pacing, HttpUser, LoadTestShape, tag
from locust.contrib.fasthttp import FastHttpUser 
import timeit
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import namedtuple, OrderedDict
from copy import copy
import sys

import logging
from queries import Query
from scenarios import *
from atomic_queries import _login, _query_high_speed_ticket

datestr = time.strftime("%Y-%m-%d", time.localtime())


target_apis = ["high_speed_ticket", "normal_speed_ticket", "query_cheapest", "query_min_station", "query_quickest", "query_order", "query_order_other", "query_route", "query_food", "enter_station", "query_contact", "preserve_normal", "query_payment"]

CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW = 2
CachedResponseTimes = namedtuple("CachedResponseTimes", ["response_times", "num_requests"])

def run_stat(stats_module):
    while True:
        time.sleep(1)
        print("---")
        print(stats_module.current_rps())
        print(stats_module.current_fail())

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        out = ""
        for api in target_apis:
            latency = mapStats[api].get_current_response_time_percentile()
            if latency == None:
                latency = 0
            latency99 = mapStats[api].get_current_response_time_percentile(0.99)
            if latency99 == None:
                latency99 = 0
            out += f"{api}={mapStats[api].current_rps()}={mapStats[api].current_fail()}={latency}={latency99}/"
        self.wfile.write(out.encode('utf-8'))

def run_server():
    port = int(input())
    httpd = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f'Server running on port:{port}')
    httpd.serve_forever()

t = threading.Thread(target=run_server, args=())
t.start()

def calculate_response_time_percentile(response_times, num_requests: int, percent: float) -> int:
    """
    Get the response time that a certain number of percent of the requests
    finished within. Arguments:
    response_times: A StatsEntry.response_times dict
    num_requests: Number of request made (could be derived from response_times,
                  but we save some CPU cycles by using the value which we already store)
    percent: The percentile we want to calculate. Specified in range: 0.0 - 1.0
    """
    num_of_request = int(num_requests * percent)

    processed_count = 0
    for response_time in sorted(response_times.keys(), reverse=True):
        processed_count += response_times[response_time]
        if num_requests - processed_count <= num_of_request:
            return response_time
    # if all response times were None
    return 0

def diff_response_time_dicts(latest, old):
    """
    Returns the delta between two {response_times:request_count} dicts.
    Used together with the response_times cache to get the response times for the
    last X seconds, which in turn is used to calculate the current response time
    percentiles.
    """
    new = {}
    for t in latest:
        diff = latest[t] - old.get(t, 0)
        if diff:
            new[t] = diff
    return new

class StatsModule:
    def __init__(self, name, window=2):
        self.name = name
        
        self.num_reqs_per_sec = {}
        self.fail_reqs_per_sec = {}
        self.response_times = {}

        self.last_request_timestamp = 0
        self.start_time = time.time()
        self.window = window
        self.num_requests = 0

        self.response_times_cache = OrderedDict()
        self.cache_response_times(int(time.time()))


    
    def log_request(self, succ, response_time):
        t = int(time.time())
        self.num_requests += 1

        self.num_reqs_per_sec[t] = self.num_reqs_per_sec.setdefault(t, 0) + 1
        if not succ:
            self.fail_reqs_per_sec[t] = self.fail_reqs_per_sec.setdefault(t, 0) + 1

        if self.last_request_timestamp != 0 and t > int(self.last_request_timestamp):
            # see if we shall make a copy of the response_times dict and store in the cache
            self.cache_response_times(t - 1)

        self.last_request_timestamp = t

        if response_time < 100:
            rounded_response_time = round(response_time)
        elif response_time < 1000:
            rounded_response_time = round(response_time, -1)
        elif response_time < 10000:
            rounded_response_time = round(response_time, -2)
        else:
            rounded_response_time = round(response_time, -3)

        # increase request count for the rounded key in response time dict
        self.response_times.setdefault(rounded_response_time, 0)
        self.response_times[rounded_response_time] += 1

    def cache_response_times(self, t: int) -> None:
        if self.response_times_cache is None:
            self.response_times_cache = OrderedDict()

        self.response_times_cache[t] = CachedResponseTimes(
            response_times=copy(self.response_times),
            num_requests=self.num_requests,
        )

        # We'll use a cache size of CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW + 10 since - in the extreme case -
        # we might still use response times (from the cache) for t-CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW-10
        # to calculate the current response time percentile, if we're missing cached values for the subsequent
        # 20 seconds
        cache_size = CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW + 10

        if len(self.response_times_cache) > cache_size:
            # only keep the latest 20 response_times dicts
            for _ in range(len(self.response_times_cache) - cache_size):
                self.response_times_cache.popitem(last=False)


    def get_current_response_time_percentile(self, percent=0.95):
        """
        Calculate the *current* response time for a certain percentile. We use a sliding
        window of (approximately) the last 10 seconds (specified by CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW)
        when calculating this.
        """
        t = int(time.time())

        acceptable_timestamps: List[int] = []
        acceptable_timestamps.append(t - CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW)
        for i in range(1, 9):
            acceptable_timestamps.append(t - CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW - i)
            acceptable_timestamps.append(t - CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW + i)

        cached: Optional[CachedResponseTimes] = None
        if self.response_times_cache is not None:
            for ts in acceptable_timestamps:
                if ts in self.response_times_cache:
                    cached = self.response_times_cache[ts]
                    break

        if cached:
            return calculate_response_time_percentile(
                diff_response_time_dicts(self.response_times, cached.response_times),
                self.num_requests - cached.num_requests,
                percent,
            )
        # if time was not in response times cache window
        return None
    
    def current_rps(self):
        if self.last_request_timestamp == 0:
            return 0
        
        slice_start_time = max(int(time.time()) - self.window, int(self.start_time or 0))

        reqs: List[int | float] = [
            self.num_reqs_per_sec.get(t, 0) for t in range(slice_start_time, int(self.last_request_timestamp))
        ]
        if len(reqs) == 0:
            return 0
        return sum(reqs) / len(reqs)

    def current_fail(self):
        if self.last_request_timestamp == 0:
            return 0
        
        slice_start_time = max(int(time.time()) - self.window, int(self.start_time or 0))

        reqs: List[int | float] = [
            self.fail_reqs_per_sec.get(t, 0) for t in range(slice_start_time, int(self.last_request_timestamp))
        ]
        if len(reqs) == 0:
            return 0
        return sum(reqs) / len(reqs)


mapStats = {}
for api in target_apis:
    mapStats[api] = StatsModule(api)

req_stat={}
def request_handler(request_type, name, response_time, succ=True):
    mapStats[name].log_request(succ, response_time)

@events.request_success.add_listener
def mySuccessHandler(request_type, name, response_time, response_length, **kw):
    if name == "login":
        return
    request_handler(request_type, name, response_time, succ=True)

@events.request_failure.add_listener
def myFailureHandler(request_type, name, response_time, response_length, **kw):
    if name == "login":
        return
    request_handler(request_type, name, response_time, succ=False)

@events.test_stop.add_listener
def myTestStop(environment):
    with open("req_stat.log", 'w') as f:
        json.dump(req_stat, f)
    print("[BK] Result saved.")


hostname = "http://10.8.0.4:32677"
usernames = ["James", "Tom", "Jimmy", "Anne"]

class WebsiteUser(HttpUser):
    wait_time = constant_throughput(1)
    network_timeout = 5.0

    def on_start(self):
        self.client.proxies = {"http": "http://10.8.0.4:8090"}
        self.client.verify = False

    @tag('cluster1')
    @tag('high_speed_ticket')
    @task(1)
    def query_high_speed_ticket(self):
        q = Query(hostname, self.client)
        # q.login()

        # Query ticket
        url = hostname + "/api/v1/travelservice/trips/left"
        place_pairs = [("Shang Hai", "Su Zhou"),
                       ("Su Zhou", "Shang Hai"),
                       ("Nan Jing", "Shang Hai")]
        place_pair = random.choice(place_pairs)
        time = datestr
        payload = {
            "departureTime": time,
            "startingPlace": place_pair[0],
            "endPlace": place_pair[1],
        }
        with q.session.post(url=url, headers={}, json=payload, catch_response=True, name='high_speed_ticket') as response:
            if not response.ok:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
            else:
                response.success()
    
    @tag('cluster1')
    @tag("query_order")
    @task(10)
    def query_order_all(self):
        q = Query(hostname, self.client)
        url = hostname + "/api/v1/orderservice/order/refresh"

        payload = {
            "loginId": q.uid,
        }
        with q.session.post(url=url, headers={}, json=payload, catch_response=True, name='query_order') as response:
            if not response.ok:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
            else:
                response.success()

    @tag('cluster1')
    @tag('query_food')
    @task(10)
    def query_food(self):
        q = Query(hostname, self.client)

        place_pair = ("Shang Hai", "Su Zhou")
        train_num = "D1345"
        url = f"{hostname}/api/v1/foodservice/foods/2021-07-14/{place_pair[0]}/{place_pair[1]}/{train_num}"

        with q.session.get(url=url, headers={}, catch_response=True, name='query_food') as response:
            if not response.ok:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
            else:
                response.success()    


    @tag("query_payment")
    @tag('cluster2')
    @task(10)
    def query_payment(self):
        q = Query(hostname, self.client)
        q.login()
        url = hostname + "/api/v1/orderOtherService/orderOther/refresh"

        payload = {
            "loginId": q.uid,
        }

            pair = ("5ad7750b-a68b-49c0-a8c0-32776b067703", "G1237")

        url = f"{hostname}/api/v1/inside_pay_service/inside_payment"
        payload = {
            "orderId": pair[0],
            "tripId": pair[1]
        }
        for i in range(5):
            with q.session.post(url=url, headers={}, json=payload, catch_response=True, name='query_payment') as response2:
                if not response2.ok:
                    response2.failure(response2.status_code)
                    return
                elif response2.elapsed.total_seconds() > 1:
                    response2.failure("Too long")
                else:
                    response2.success()

    @tag("normal_speed_ticket")
    @tag('cluster2')
    @task(1)
    def query_normal_speed_ticket(self):
        q = Query(hostname, self.client)

        # Query ticket
        url = hostname + "/api/v1/travel2service/trips/left"
        place_pairs = [("Shang Hai", "Tai Yuan"),
                        ("Nan Jing", "Bei Jing"),
                        ("Tai Yuan", "Shang Hai")]
        place_pair = random.choice(place_pairs)
        time = datestr
        payload = {
            "departureTime": time,
            "startingPlace": place_pair[0],
            "endPlace": place_pair[1],
        }
        with q.session.post(url=url, headers={}, json=payload, catch_response=True, name='normal_speed_ticket') as response:
            if not response.ok:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
            else:
                response.success()

    @tag("query_order_other")
    @tag('cluster2')
    @task(10)
    def query_order_other_all(self):
        q = Query(hostname, self.client)
        url = hostname + "/api/v1/orderOtherService/orderOther/refresh"

        payload = {
            "loginId": q.uid,
        }

        with q.session.post(url=url, headers={}, json=payload, catch_response=True, name='query_order_other') as response:
            if not response.ok:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
            else:
                response.success()
    
    @task(1)
    @tag("query_cheapest")
    def query_ticket_cheapest(self):
        q = Query(hostname, self.client)
        url = hostname + "/api/v1/travelplanservice/travelPlan/cheapest"
        place_pairs = [("Nan Jing", "Shang Hai")]

        place_pair = random.choice(place_pairs)

        date = datestr

        payload = {
            "departureTime": date,
            "startingPlace": place_pair[0],
            "endPlace": place_pair[1],
        }
        with q.session.post(url=url, headers={}, json=payload, catch_response=True, name='query_cheapest') as response:
            if not response.ok:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
            else:
                response.success()
    @task(1)
    def query_contacts(self):
        q = Query(hostname, self.client)
        q.login()

        contacts_url = f"{hostname}/api/v1/contactservice/contacts/account/{q.uid}"
        with q.session.get(url=contacts_url, headers={}, catch_response=True, name='query_contact') as response2:
            if not response2.ok:
                response2.failure(response2.status_code)
                return
            elif response2.elapsed.total_seconds() > 1:
                response2.failure("Too long")
            else:
                response2.success()        


    @tag('cluster5')
    @task(1)
    def query_route(self):
        q = Query(hostname, self.client)
        url = hostname + "/api/v1/routeservice/routes"

        with q.session.get(url=url, headers={}, catch_response=True, name='query_route') as response:
            if not response.ok:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
            else:
                response.success()



    @tag('cluster3')
    @task(1)
    def query_and_execute(self):
        q = Query(hostname, self.client)
        q.login()

        url = hostname + "/api/v1/orderservice/order/refresh"

        payload = {
            "loginId": q.uid,
        }

        with q.session.post(url=url, headers={}, json=payload, catch_response=True, name='query_order') as response:
            if response.status_code == 403:
                response.failure(response.status_code)
                return
            elif response.elapsed.total_seconds() > 1:
                response.failure("Too long")
                data = response.json().get("data")
            else:
                response.success()
                data = response.json().get("data")
        
            pairs = []
            if data == None:
                return
            for d in data:
                # status = 0: not paid
                # status=1 paid not collect
                # status=2 collected
                if d.get("status") in [0, 1]:
                    order_id = d.get("id")
                    trip_id = d.get("trainNumber")
                    pairs.append((order_id, trip_id))

            if len(pairs) == 0:
                return
            pair = random.choice(pairs)


            url = f"{hostname}/api/v1/executeservice/execute/execute/{pair[0]}"
            with q.session.get(url=url, headers={}, catch_response=True, name='enter_station') as response:
                if not response.ok:
                    response.failure(response.status_code)
                    return
                elif response.elapsed.total_seconds() > 1:
                    response.failure("Too long")
                else:
                    response.success()