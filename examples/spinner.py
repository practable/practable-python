#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import matplotlib.pyplot as plt
import numpy as np
from practable.book import Experiment
import time

messages = []
   
#modify with actual group code and experiment name
with Experiment('g-open-x3fca8','Spinner 51 (Open Days)', exact=True) as expt:
    
    # Command a step of 2 radians & collect the data
    expt.command('{"set":"mode","to":"stop"}')
    expt.command('{"set":"mode","to":"position"}')
    expt.command('{"set":"parameters","kp":1,"ki":0,"kd":0}')

    time.sleep(0.5)
        
    expt.command('{"set":"position","to":2}')    
    
    expt.ignore(0.5)
    messages = expt.collect(1.5)
    
    # Process the data
    ts = expt.extract_series(messages, "t")
    ds = expt.extract_series(messages, "d")
    cs = expt.extract_series(messages, "c")
    
    t = np.array(ts)
    t = t - t[0]
    
    # Plot the data
    plt.figure()        
    plt.plot(t/1e3,ds,'-b',label="position")
    plt.plot(t/1e3,cs,':r',label="set point")
    plt.xlabel("time(s)")
    plt.ylabel("position(rad)")
    plt.legend()