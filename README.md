# practable-python
a library for connecting to experiments in python

## Requirements

book:
```
expt = practable.book(group, duration, [, type="spin"| name="spin32"])
```

experiment:

```
expt.streams()
```

list the streams the experiment has

```
stream = expt.connect(stream_name) 
```
connect to experiment stream

```
stream.ok()
```
check if stream is connected, within the session time


Stream should be a generator (iterator) with ability to send and receive messages

```
next(stream)

stream.send(message)
```



