#!/usr/bin/python
import random

# pick 3910

def pick_ints(count):
    values = list(range(0, 100000))

    print(len(values))

    def pick_one():
        r = random.randint(0, len(values))
        v = values[r]
        del values[r]
        return v

    q = []
    for a in range(count):
        q.append(pick_one())

    print("count: ", count, " anser:", q)


pick_ints(10)
pick_ints(100)
pick_ints(1000)
pick_ints(10000)
