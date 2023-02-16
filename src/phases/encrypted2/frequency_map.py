# frequency_map.py

import re
import sys
import yaml
import random

import dataStructures

regex = r"map_(\w+)_f(\d+)"

def load_map(file_name: str):

    with open(file_name) as fh:
        map_file = yaml.load(fh, yaml.FullLoader)

    freq_map = {}

    for k in map_file.keys():
        if k.startswith("map"):
            # print("k:" + k)
            m = re.match(regex, k)
            coll = m[1]
            field_num = int(m[2])
            # print(m[1], m[2])
            freq_map[field_num ] = map_file[k]["from"]

    return freq_map

def get_bucket_name(c, v: int):
    for k_r in c.ranges.keys():
        r = c.ranges[k_r]
        # print(r)
        if r.__contains__(v):
            return k_r
    else:
        raise ValueError()

class FrequencyBuckets:
    def __init__(self, freq_map):
        self.full_map = freq_map
        self.buckets = {}

        # Subdivide the map into buckets
        c = dataStructures.Config()

        for k in self.full_map.keys():
            # print(k)
            count = self.full_map[k]
            # print(count)

            bucket = get_bucket_name(c, count)

            if bucket not in self.buckets:
                self.buckets[bucket] = []

            self.buckets[bucket].append((k, count))

    def fixed_value(self):
        bucket = random.randint(0, len(self.full_map) - 1)
        return list(self.full_map.keys())[bucket]

    def fixed_bucket(self, bucket):
        items_list = self.buckets[bucket]
        if bucket in ["vlf", "mlf", "mf"]:
            return min(items_list, key= lambda x: x[1])[0]
        else:
            return max(items_list, key= lambda x: x[1])[0]

    def uar(self):
        return list(self.full_map.keys())

    def uar_bucket(self, bucket):
        return [x[1] for x in self.buckets[bucket]]

    def uar_all_low(self):
        return self.uar_bucket("vlf") + self.uar_bucket("mlf") + self.uar_bucket("lf")

    def uar_all_high(self):
        return self.uar_bucket("hf") + self.uar_bucket("mhf") + self.uar_bucket("hf")

def main():
    a = load_map("maps_pbl.yml")

    print(a[1])

    b  = FrequencyBuckets(a[1])

    print(b.buckets)

    print("FV:" + b.fixed_value())
    print("FV:" + b.fixed_bucket("hf"))

if __name__== "__main__":
    main()
