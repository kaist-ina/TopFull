import gym, ray
from ray.rllib.algorithms import ppo

import random
import numpy as np
from skeleton_simulator import *
# from multi_api_simulator import *
from metric_collector import *
from overload_detection import *
import time



N_DISCRETE_ACTIONS = 5
feature = 2
MAX_STEPS = 50

#collector = Collector(code="online_boutique")
target_api = "query_order"

class MyEnv(gym.Env):
    def __init__(self, env_config):
        self.action_space = gym.spaces.Box(low=np.array([-0.5]), high=np.array([0.5]), dtype=np.float32)
        self.observation_space = gym.spaces.Box(low=np.array([-2000.0, -1000.0]), high=np.array([2000.0, 50000.0]), dtype=np.float32)
        self.MAX_STEPS = MAX_STEPS

    def reset(self):
        self.detector = Detector()
        self.collector = Collector(code="train_ticket")
        self.ts = Simulator()
        self.detector.apis[target_api]['threshold'] = 1000
        self.detector.reset([target_api])
        time.sleep(5)

        self.count = 0
        metric = self.collector.query()
        rps, fail, init_latency = metric[target_api]

        self.detector.apis[target_api]['threshold'] = rps
        self.threshold = rps
        self.detector.reset([target_api])
        self.goodput = rps - fail

        self.state = np.array([(rps - fail)/rps, init_latency])
        self.reward = 0
        self.done = False
        self.info = {}
        return self.state

    def step(self, action):
        if self.done:
            print("EPISODE DONE!!!") 
        elif self.count == self.MAX_STEPS:

            self.done = True
        else:
            self.count += 1
            metric = self.collector.query()
            rps, fail, latency = metric[target_api]
            tmpGoodput = rps - fail

            new_threshold = (1 + float(action)) * self.threshold
            if new_threshold <= 10:
                new_threshold = 10
            if new_threshold > rps * 1.1:
                new_threshold = rps * 1.1

            self.detector.apis[target_api]['threshold'] = new_threshold
            apply_threshold_proxy([self.detector.apis[target_api]])

            time.sleep(1)

            metric = self.collector.query()
            rps, fail, latency = metric[target_api]
            self.goodput = rps - fail

            deltaGoodput = self.goodput - tmpGoodput
            self.threshold = self.detector.apis[target_api]['threshold']
            
            goodputPerThres = self.goodput/self.threshold

            self.state = np.array([goodputPerThres, latency])
            self.reward = deltaGoodput
            if latency > 1000:
                self.reward -= latency*0.01
 

        return self.state, self.reward, self.done, self.info



ray.init()
algo = ppo.PPO(env=MyEnv, config={
    "env_config": {},  # config to pass to env class
    'num_workers': 0,
})
checkpoint_path = "./checkpoint_000701"
algo.restore(checkpoint_path)


_ = 0
while True:
    if _ % 1 == 0:
        algo.save("./models_transfer/v1tmp1/rllib_checkpoint")
        print(_)
    _ += 1
    print(algo.train()['episode_reward_mean'])
