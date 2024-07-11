import gym, ray
from ray.rllib.algorithms import ppo

import random
import numpy as np
from skeleton_simulator import *
# from multi_api_simulator_simulator import *
from log_parser import _getRawData, _getStatisticsFromData


N_DISCRETE_ACTIONS = 5
feature = 2
MAX_STEPS = 50
addstep = 5
mulstep = 0.1

class MyEnv(gym.Env):
    def __init__(self, env_config):
        self.action_space = gym.spaces.Discrete(N_DISCRETE_ACTIONS)
        self.observation_space = gym.spaces.Box(low=np.array([-2000.0, -1000.0]), high=np.array([2000.0, 50000.0]), dtype=np.float32)
        self.MAX_STEPS = MAX_STEPS
        self.addstep = addstep
        self.mulstep = mulstep

    def reset(self):
        self.ts = Simulator(addstep,mulstep)
        self.goodput = self.ts.currGoodput
        self.maxgoodput = self.ts.targetGoodput
        self.count = 0
        self.stopcount = 0
        initdelta = self.ts.simGoodput(0) - self.goodput
        self.state = np.array([initdelta, self.ts.simLatency(0)])
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
            tmpGoodput = self.goodput
            self.goodput = self.ts.simGoodput(action)
            latency = self.ts.simLatency(action)

            goodputPerThres = self.goodput/self.ts.thresGoodput
            self.state = np.array([goodputPerThres, latency])
            self.reward = deltaGoodput

            if latency > 1100:
                self.reward -= latency*0.01

        return self.state, self.reward, self.done, self.info



ray.init()
algo = ppo.PPO(env=MyEnv, config={
    "env_config": {},  # config to pass to env class
})

_ = 0
while True:
    print(algo.train()['episode_reward_mean'])
    if _ % 50 == 0:
        algo.save("./models/v1tmp1/rllib_checkpoint")
        print(_)
    _ += 1