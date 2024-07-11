import numpy as np
import os
from collections import OrderedDict as OD
import itertools
import json


def _getStatisticsFromData(type, data, digit=1):
    arr = np.array(data)
    if type == "max":
        return round(np.max(arr), digit)
    elif type == "min":
        return round(np.min(arr), digit)
    elif type == "avg":
        return round(np.average(arr), digit)
    elif type == "std":
        return round(np.std(arr), digit)
    elif type == "var":
        return round(np.var(arr), digit)
    elif not isinstance(type, int) and not isinstance(type, float):
        return -1
    else:
        return round(np.percentile(arr,type),digit)


def _getRawData(state_max, workloads, dirPath="./"):
    print(" Loading raw data...")
    if not workloads:
	    print(" No workloads list input!")
	    raise ValueError

    ret = OD()
    for workload in workloads:
        ret[workload] = [[[OD({"raw": [], "stat": OD()}) for _ in range(state_max)] for _ in range(state_max)] for _ in
                         range(state_max)]

        for p, d, r in itertools.product(range(state_max, 0, -1), range(state_max, 0, -1), range(state_max, 0, -1)):
            file_name = "{}bookinfo_{}{}{}1_{}.latency.log".format(dirPath, p, d, r, workload)
            with open(file_name, 'r') as f:
                for line in f:
                    latency = float(str(line).split(' ')[0])
                    ret[workload][p-1][d-1][r-1]["raw"].append(latency)
    return ret

def calcLatencyStat(data, workloads, statList, state_max):
    print(" Calculating stats...")
    for workload in workloads:
        for p, d, r in itertools.product(range(state_max, 0, -1), range(state_max, 0, -1), range(state_max, 0, -1)):
            for stat in statList:
                data[workload][p-1][d-1][r-1]["stat"][stat] = _getStatisticsFromData(stat, data[workload][p-1][d-1][r-1]["raw"])

    return data

def getRawData(statList, state_max=5, workloads=None, dirPath="./", serialName="parsed.dict"):
    print("Loading logs...")
    filePath = "{}{}".format(dirPath, serialName)
    if os.path.isfile(filePath):
        print(" Loading parsed data...")
        with open(filePath, "r") as f:
            ret = json.load(f)
        print(" Done.")
        return ret

    # loads raw data
    data = _getRawData(state_max, workloads, dirPath=dirPath)

    # calculate latency statistics
    ret = calcLatencyStat(data, workloads, statList, state_max)

    print(" Saving parsed data... (might take 2-3 minutes)")
    with open(filePath, "w") as f:
        json.dump(ret, f)
    print(" Done.")

    return ret
