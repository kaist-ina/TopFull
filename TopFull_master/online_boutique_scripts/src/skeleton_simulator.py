from sre_parse import State
from statistics import mean
import numpy as np
import os
from collections import OrderedDict as OD
import itertools
import json
import random


class Simulator:
    # initial latency
    # initial incoming goodput
    # initial threshold
    # maximal possible goodput (visible only to the simulator)
    def __init__(self, addstep, mulstep):
        self.latency = random.uniform(150, 5000)
        initthres = random.uniform(0.3, 1.7)
        self.targetGoodput = random.uniform(50, 500)
        self.referenceLatency = random.uniform(10,300)
        self.targetLatency = 1000
        self.overloadLatency = random.uniform(5000,20000)
        self.thresGoodput = self.targetGoodput * initthres
        self.currGoodput = min(self.thresGoodput, self.targetGoodput*(1-(self.thresGoodput-self.targetGoodput)/self.targetGoodput))
        self.addstep = addstep
        self.mulstep = mulstep

    def simGoodput(self, action):
        self.thresGoodput = (1+float(action)) * self.thresGoodput
        goodput = self.expGoodput(self.targetGoodput, self.thresGoodput)
        
        return goodput


    def simLatency(self, action):
        if self.thresGoodput < self.targetGoodput * 0.5:
            self.latency = self.referenceLatency + abs(self.noiseLatency())
        elif self.thresGoodput < self.targetGoodput *0.7:
            self.latency = (self.referenceLatency + abs(self.noiseLatency()))*1.5
        elif self.thresGoodput < self.targetGoodput *1.0:
            self.latency = self.targetLatency + abs(self.noiseLatency())
        elif self.thresGoodput < self.targetGoodput *1.3:
            self.latency = (self.targetLatency + abs(self.noiseLatency()))*1.5
        elif self.thresGoodput < self.targetGoodput *1.5:
            self.latency = (self.targetLatency + abs(self.noiseLatency()))*2
        elif self.thresGoodput < self.targetGoodput *2.0:
            self.latency = (self.targetLatency + abs(self.noiseLatency()))*3
        else:
            self.latency = self.overloadLatency + self.noiseLatency() * 100
        return min (self.latency, 40000)        

    def expGoodput(self, target, thres):
        if thres <= target*0.7:
            return thres + self.noise()
        elif thres <= target:
            return thres * self.overloadnoise(bottom=0.98, top=1.01)
        elif thres <= target*1.1:
            return target * max(0, (1 - (thres-target)/target)) *self.overloadnoise(bottom=0.95, top=1.03)
        elif thres <= target*1.2:
            return target * max(0, (1 - (thres-target)/target)) *self.overloadnoise(bottom=0.9, top=1.08)
        else:
            return target * max(0, (1 - (thres-target)/target)) *self.overloadnoise(bottom=0.8, top=1.15)
    
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

    def overloadnoise(self, bottom=0.98, top=1.01):
        overloadnoise = random.uniform(bottom, top)
        return overloadnoise

    def noiseLatency(self, mean=0, std=5):
        noiseLatency = random.normalvariate(mean, std)
        return noiseLatency

    def noisedata(self, path):
        ##load from collected data
        ##calculate mean and standard deviation from the data
        return noise