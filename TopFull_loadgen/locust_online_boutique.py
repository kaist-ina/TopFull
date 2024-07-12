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
#import locust.stats
#locust.stats.CSV_STATS_INTERVAL_SEC = 1 # default is 2 seconds
import sys

products = [
    '0PUK6V6EV0',
    '1YMWWN1N4O',
    '2ZYFJ3GM2N',
    '66VCHSJNUP',
    '6E92ZMYYFZ',
    '9SIQT8TOJO',
    'L9ECAV7KIM',
    'LS4PSXUNUM',
    'OLJCESPC7Z']

target_apis = ["postcheckout", "getproduct", "getcart", "postcart", "emptycart"]
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
            latency95 = mapStats[api].get_current_response_time_percentile()
            latency99 = mapStats[api].get_current_response_time_percentile(percent=0.99)
            if latency95 == None:
                latency95 = 0
            if latency99 == None:
                latency99 = 0
            out += f"{api}={mapStats[api].current_rps()}={mapStats[api].current_fail()}={latency95}={latency99}/"
        #print(out)
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

        

mapStats = {
    "postcheckout": StatsModule("postcheckout"),
    "getproduct": StatsModule("getproduct"),
    "getcart": StatsModule("getcart"),
    "postcart": StatsModule("postcart"),
    "emptycart": StatsModule("emptycart")
}

# t = threading.Thread(target=run_stat, args=(mapStats["getproduct"],))
# t.start()

req_stat={}
def request_handler(request_type, name, response_time, succ=True):
    mapStats[name].log_request(succ, response_time)

@events.request_success.add_listener
def mySuccessHandler(request_type, name, response_time, response_length, **kw):
    request_handler(request_type, name, response_time, succ=True)

@events.request_failure.add_listener
def myFailureHandler(request_type, name, response_time, response_length, **kw):
    request_handler(request_type, name, response_time, succ=False)

@events.test_stop.add_listener
def myTestStop(environment):
    with open("req_stat.log", 'w') as f:
        json.dump(req_stat, f)
    print("[BK] Result saved.")

goodput_threshold = {
    "getcart": 1,
    "setcurrency": 10,
    "postcart": 1,
    "postcheckout": 1,
    "getproduct": 1,
    "emptycart": 1
}

checkout_body = {
        'email': 'someone@example.com',
        'street_address': '1600 Amphitheatre Parkway',
        'zip_code': '94043',
        'city': 'Mountain View',
        'state': 'CA',
        'country': 'United States',
        'credit_card_number': '4432-8015-6152-0454',
        'credit_card_expiration_month': '1',
        'credit_card_expiration_year': '2039',
        'credit_card_cvv': '672',
    }

rand_url = "/random/1"

class WebsiteUser(HttpUser):
    wait_time = constant_throughput(1)

    def on_start(self):
        self.client.proxies = {"http": "http://10.8.0.4:8090"}
        self.client.verify = False
    
    @tag('postcheckout')
    @task(50)
    def checkout_slow(self):

        with self.client.post("/cart/checkout", checkout_body, catch_response=True, name="postcheckout") as response:
            if response.elapsed.total_seconds() > goodput_threshold["postcheckout"]:
                response.failure("Too long")
            elif not response.ok:
                response.failure(response.status_code)
            else:
                response.success()

    @tag('getcart')
    @task(30)
    def viewCart_slow(self):
        with self.client.get("/cart", catch_response=True, name="getcart") as response:
            if response.elapsed.total_seconds() > goodput_threshold["getcart"]:
                response.failure("Too long")
            elif not response.ok:
                response.failure(response.status_code)
            else:
                response.success()

            

    @tag('postcart')
    @task(15)
    def addToCart_slow(self):
        product = random.choice(products)
        with self.client.post("/cart", {"product_id": product, "quantity": random.choice([1,2,3,4,5,10])}, catch_response=True, name="postcart") as response:
            if response.elapsed.total_seconds() > goodput_threshold["postcart"]:
                response.failure("Too long")
            elif not response.ok:
                response.failure(response.status_code)
            else:
                response.success()

    @tag('emptycart')
    @task(15)
    def emptyCart_slow(self):
        with self.client.post("/cart/empty", catch_response=True, name="emptycart") as response:
            if response.elapsed.total_seconds() > goodput_threshold["emptycart"]:
                response.failure("Too long")
            elif not response.ok:
                response.failure(response.status_code)
            else:
                response.success()
    
    @tag('getproduct')
    @task(150)
    def browseProduct_slow(self):
        headers = {
            "priority": str(random.randint(0, 99))
        }
        with self.client.get("/product/"+products[0], headers=headers, catch_response=True, name="getproduct") as response:
            if response.elapsed.total_seconds() > goodput_threshold["getproduct"]:
                response.failure("Too long")
            elif not response.ok:
                response.failure(response.status_code)
            else:
                response.success()
