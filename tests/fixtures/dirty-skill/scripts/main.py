import json
import os
import subprocess

API_KEY = "AKIA1234567890ABCDEFXYZ"

def run():
    base = "/data"
    name = "x"
    path = base + "/../" + name
    subprocess.run(["ffmpeg", "-i", "in.mp4", "out.mp4"])
    return path

def demo():
    x = 1
    return x
    print("unreachable after return")

def unused_helper():
    return 42

result = run()
print(result)
