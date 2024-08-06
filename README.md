# practable-python
a library for connecting to experiments in python


## Example Usage

```
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
```


This script produces the following text output
```
Command: {"set":"mode","to":"stop"}
Command: {"set":"mode","to":"position"}
Command: {"set":"parameters","kp":1,"ki":0,"kd":0}
Command: {"set":"position","to":2}
Ignoring messages for 0.5 seconds |██████████████████████████████████████████████████| 100.0% Complete

Collecting messages for 1.5 seconds |██████████████████████████████████████████████████| 100.0% Complete

```
An a graph:

![Example graphic from a spinner](./img/spinner.jpg)

## Additional information

A user name is obtained and stored locally.

Bookings last only as long as the experiment is needed, because they are cancelled when the `with` environment exits. The default booking duration is 3 min.

You can use an existing booking by specifying `user="cxxxxxxxxxx"` where the username is found on the `user` tab of the booking system that holds the booking.

Other `practable` instances can be accessed by specifying it e.g. `booking-server="https://some.booking.server"`

## Requirements

Recommend python >= 3.8 because we're using websockets 12.0





