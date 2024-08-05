#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 13:36:13 2024

Booker class handles logging into a booking server and making bookings
The user name is stored in the user's configuration directory, or in cwd

@author: tim

"""

from datetime import datetime, timedelta, UTC
import json
import math
import matplotlib.pyplot as plt
import numpy as np
import os.path
from platformdirs import user_config_dir
from pathlib import Path
from queue import Queue
import random
import requests
import time
from urllib.parse import urlparse

from websockets.sync.client import connect as wsconnect

class Booker:
    
    def __init__(self, book_server="https://app.practable.io/ed0/book", config_in_cwd=False):

        self.book_server = book_server
        
        # create a configuration directory for the book_server
        # some users may use more than one booking server so keep them separate
        # config can be stored in current working directory instead, by setting 
        # config_in_cwd=True when initialising; this may be helpful for
        # Jupyter notebooks
        
        u = urlparse(book_server)
        self.activities={}
        self.background_tasks = set() #strong ref to stop coros being gargage collected early  https://docs.python.org/3/library/asyncio-task.html#id4
        self.host = u.netloc
        self.app_author = "practable" 
        self.app_name = "practable-python-" + u.netloc.replace(".","-") + u.path.replace("/","-")
        self.bookings=[]
        self.groups=[]
        self.group_details={}
        self.experiments=[]
        self.experiment_details={}
        
        if config_in_cwd: #for jupyter notebooks
            self.ucd = os.getcwd()
        else:
            self.ucd = user_config_dir(self.app_name, self.app_author)
            Path(self.ucd).mkdir(parents=True, exist_ok=True)
                
        # login to the booking system
        self.exp =datetime.now() #set value for login expiry to trigger login
        self.ensure_logged_in()
        
    def __str__(self):
        if self.exp > datetime.now():
            return f"user {self.user} logged in to {self.book_server} until {self.exp}"
        else:
            return f"user {self.user} not logged in to {self.book_server}"
    
    def add_group(self,group):
        self.ensure_logged_in()
        url = self.book_server + "/api/v1/users/" + self.user + "/groups/" + group
        r = requests.post(url, headers=self.headers)     
        
        if r.status_code != 204:
           print(r.status_code)
           print(r.text)
           raise Exception("could not add group %s"%(group))
        
        self.groups.append(group)
           
    def book(self, duration, selected=""):
        
        if not isinstance(duration, timedelta):
            raise TypeError("duration must be a datetime.timedelta")

        start =  datetime.now(UTC)
        end = start + duration
        
        if selected == "":
            # if  none specified, select an experiment from self.available
            # note: use filter_experiments to set self.available
            if len(self.available) < 1:
                if self.filter_number == "":
                    raise Exception("There are no available experiments matching `%s`"%(self.filter_name))            
                else:
                    raise Exception("There are no available experiments matching `%s` number `%s`"%(self.filter_name,self.filter_number))  
                    
            # book a random selection from the available list
            selected = random.choice(self.available)
        
        # make the booking
        slot = self.experiment_details[selected]["slot"]
        url = self.book_server + "/api/v1/slots/" + slot 
        params             ={"user_name": self.user,
                             "from": start.isoformat(),
                             "to": end.isoformat(),
                             }    
        
        r = requests.post(url,params=params, headers=self.headers)  
        
        if r.status_code != 204:
            print(r.status_code)
            print(r.text)
            raise Exception("could not book %s for %s"%(selected, duration))
    
    def cancel_booking(self, name):
        
        url = self.book_server + "/api/v1/users/" + self.user + "/bookings/" + name
        
        r = requests.delete(url, headers=self.headers)  
        
    
        if r.status_code != 404:       
           print(r.status_code)
           print(r.text)               
           raise Exception("could not cancel booking %s"%(name))
           
    def cancel_all_bookings(self):
        
        self.get_bookings() #refresh current bookings
        
        for booking in self.bookings:
            try:
                self.cancel_booking(booking["name"])
            except:
                pass #ignore the case where we get 500 can't cancel booking that already ended
            
        self.get_bookings()
        
        if len(self.bookings) > 0:
            raise Exception("unable to cancel all bookings")
            
    def check_slot_available(self, slot):
        url = self.book_server + "/api/v1/slots/" +  slot
        r = requests.get(url, headers=self.headers)  
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not get slot details for slot %s"%(slot)) 

        avail = r.json()
        if len(avail) < 1:
           available_now=False
           when=[]
        else:
           start = datetime.fromisoformat(avail[0]["start"])
           end = datetime.fromisoformat(avail[0]["end"])
           when = {"start":start, "end":end}
           available_now = when["start"] <= (datetime.now(UTC) + timedelta(seconds=1))
           
        return available_now, when  
    
    def ensure_logged_in(self): #most booking operations take much less than a minute
    
        if not self.exp > (datetime.now() + timedelta(minutes=2)):
                  
            self.ensure_user()
            
            r = requests.post(self.book_server + "/api/v1/login/" + self.user)
            
            if r.status_code != 200:
                print(r.status_code)
                print(r.text)
                raise Exception("could not login as user %s at %s"%(self.user, self.booking_server))

            rj = r.json()
            self.exp = datetime.fromtimestamp(rj["exp"])
            self.headers ={'Content-Type':'application/json','Authorization': '{}'.format(rj['token'])}
         
  
    def ensure_user(self):
        # check if we have previously stored a user name in config dir
        try:
            f = open(os.path.join(self.ucd,'user'))
            user = f.readline()
            if user != "":
                self.user = user
                return
            
        except FileNotFoundError:
            pass
        
        #if get to here, user is not found, or empty, so get a new one
        r = requests.post(self.book_server + "/api/v1/users/unique")
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not get new user id from %s"%(self.book_server))
        user = r.json()["user_name"]    
        with open(os.path.join(self.ucd,'user'), 'w') as file:
            file.write(user)
        self.user = user 
        
    def set_user(self, user):
        
        with open(os.path.join(self.ucd,'user'), 'w') as file:
            file.write(user)
        self.user = user        
    
    def filter_experiments(self, sub, number="", exact=False):
        self.filter_name = sub
        self.filter_number = number
        self.available = []
        self.unavailable = {}
        self.listed = []
        
        if exact==True and sub in self.experiments:
            self.listed.append(sub)
            
        else:        
        
            for name in self.experiments:
                if sub in name:
                    if number == "":
                        self.listed.append(name)
                    else:
                        if number in name:
                            self.listed.append(name)
                
        for name in self.listed:
            available_now, when = self.check_slot_available(self.experiment_details[name]["slot"])
            if available_now:    
                self.available.append(name)
            else:
                self.unavailable[name]=when["start"]
                
    def get_activity(self, booking):
        #get the activity associated with a booking (use the uuid in the name field)
        url = self.book_server + "/api/v1/users/" + self.user + "/bookings/" + booking
        r = requests.put(url, headers=self.headers)      
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not get activity for booking %s"%(booking)) 
           
        #remove stale activities    
        activities = self.activities
        now = datetime.now(UTC)
        for activity in activities:
            if datetime.fromtimestamp(activity["exp"],tz=UTC) > now:
                del self.activities[activity]
                
        ad = r.json()
        # we can only link an activity with a booking at the time we request it
        # so we need to store that link in the activity to allow cancellation
        # cancelling all bookings will interfere with other instances operating
        # on the same machine
        ad["booking"]=booking #so we can identify which booking to cancel
        
        name = ad["description"]["name"]
        self.activities[name] = ad
        
    def get_all_activities(self):
        for booking in self.bookings:
            #print("getting activity for " + booking["name"] + " for " + booking["slot"])
            self.get_activity(booking["name"])
        
        
    def get_bookings(self):
        self.ensure_logged_in()
        url = self.book_server + "/api/v1/users/" + self.user + "/bookings"
        r = requests.get(url, headers=self.headers)      
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not get bookings for %s from %s"%(self.user, self.booking_server)) 
            
        bookings = r.json()
        
        now = datetime.now(UTC)
        
        self.bookings = []
        
        for booking in bookings:
            start = datetime.fromisoformat(booking["when"]["start"])
            end = datetime.fromisoformat(booking["when"]["end"])
            
            if now >= start and now <= end:
                self.bookings.append(booking)
                

    def get_group_details(self):
        self.ensure_logged_in()
        
        for group in self.groups:
            url = self.book_server + "/api/v1/groups/" + group
            r = requests.get(url, headers=self.headers)      
            if r.status_code != 200:
                print(r.status_code)
                print(r.text)
                raise Exception("could not get group details for group %s"%(group)) 
            
            gd = r.json()
            self.group_details[group] = gd
            for policy in gd["policies"].values():
                for slot in policy["slots"]:
                    v = policy["slots"][slot]
                    v["slot"] = slot
                    name = v["description"]["name"]
                    self.experiments.append(name)
                    self.experiment_details[name] = v
                    
    def connect(self, name, which="data"):
       
        stream = {}
        
        try:
            for s in self.activities[name]["streams"]:
                if s["for"]==which:
                    stream = s
        except KeyError:
            raise KeyError("activity not found for experiment %s"%(name))
            
        if stream == {}:
            raise Exception("stream %s not found"%(which))
            
        url = stream["url"]    
        token = stream["token"]
        headers = {'Content-Type':'application/json','Authorization': '{}'.format(token)}
        
        r = requests.post(url, headers = headers)
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not access %s stream %s"%(which, name))
        
        return r.json()["uri"]
    

    
class Experiment(object):
    # will only be used on one experiment at a time
    # but the underlying booker object will have the same
    # user name for all instances, so when booking many experiments
    # at the same time, each will download all the activitiees etc
    # shouldn't necessarily be an issue for general users with a few experiments
    # but for systemwide testing, it might be better to force a username with
    # a common first part like "system-tester" and then a second part that is
    # unique to the system it is running on, and then a third part that is unique
    # to the Experiment instance.
    
    # supply user name to access booking made using browser?
    # default behaviour on exit is to cancel a booking if we made it, not if it
    # already existed (e.g. was made online)
    
    #TODO add a look ahead feature for making bookings "soon" (queueing)
    #TODO consier different object for fresh booking versus prebooking as behavoour is different?
    #TODO consider adding e.g. 8 character xcvf-6311 code for each booking that a user can get from bookjs
    #     along with the necessary example code to use the booking, to simplify the information
    #     needed to connect to an existing booking; (but without becoming this id after??)
    #TODO Add a python template option on booking page
    def __init__(self, group, name, user="", book_server="", config_in_cwd=False, duration=timedelta(minutes=3), exact=False, number="", time_format="ms",time_key="t",cancel_new_booking_on_exit=True, max_wait_to_start=timedelta(minutes=1)):


        if book_server == "":
            self.booker = Booker(config_in_cwd=config_in_cwd) #use the default booking server
        else:    
            self.booker = Booker(book_server=book_server,config_in_cwd=config_in_cwd)
        
        # set a specific user, e.g. online identity used to book the kit already
        # i.e. a booking we want to use interactively without cancelling it
        if user != "":    
            self.booker.set_user(user)
            
        self.booker.add_group(group)
             
        self.duration = duration
        self.exact = exact
        self.group = group
        self.name = name
        self.number = number
        self.user = user
        self.cancel_new_booking_on_exit=cancel_new_booking_on_exit
      
    def __enter__(self):
        # see if we have an existing booking
        self.booker.get_bookings()
        self.booker.get_all_activities()
        
        try:
            self.url= self.booker.connect(self.name)
            self.cancel_booking_on_exit = False
        except KeyError:
            # make a booking
            self.booker.get_group_details()
            self.booker.filter_experiments(self.name, self.number, self.exact)
            self.booker.book(self.duration)
            self.booker.get_bookings()
            self.booker.get_all_activities()
            self.url= self.booker.connect(self.name)
            self.cancel_booking_on_exit = self.cancel_new_booking_on_exit
            
        # https://websockets.readthedocs.io/en/stable/reference/sync/client.html
        self.websocket = wsconnect(self.url)
        return self 
        
    def __exit__(self, *args):
        self.websocket.close()
        if self.cancel_booking_on_exit:
            #identify and cancel booking
            booking = self.booker.activities[self.name]["booking"]
            self.booker.cancel_booking(booking)
            
    def collect(self, count, timeout=None):
        messages = []
        collected = 0
        
        while collected < count:
            message = self.recv(timeout=timeout)
            for line in message.splitlines():
                try:
                    if line != "":
                        messages.append(json.loads(line))
                        collected += 1
                        printProgressBar(collected, count, prefix = f'Collecting {count} messages', suffix = 'Complete', length = 50)
                except json.JSONDecodeError:
                    print("Warning could not decode as JSON:" + line)
        return messages            

    def command(self, message):
        print("Command: " + message)
        self.send(message)        
                
    def recv(self, timeout=None):
        return self.websocket.recv(timeout=timeout)

    def send(self, message):
        self.websocket.send(message)
        time.sleep(0.05) #rate limiting step to ensure messages are separate

    def ignore(self, duration):
        # this needs to use the timestamps in the messages
        # ignore the data until the timestamps exceed that time
        # TODO read the timesamps
        
        endtime = datetime.now() + duration
        
        #timeout is in seconds, so round up to nearest whole seconds
        # if this is longer than we want to wait, no worries, because
        # it only times out if there was no data anyway.
        timeout = math.ceil(duration.total_seconds())
        
        count = 0
        
        while True:
            try:
                message = self.recv(timeout=timeout)
                # save message in case it is an edge case that needs us to
                # stash it

            except TimeoutError:
                # timed out, so return
                return
     
            # check for edge case, which is that:
            # if no message is received while we are ignoring
            # but then we get one after the ignore duration has expired
            # but before the timeout we created with whole number
            # seconds has expired (e.g. a message at 700ms on a 500ms ignore, 
            # which requires a 1s timeout) then 
            # we have to stash it to be received by user
            # in case there are sparsely/unevenly spaced but important 
            # messages being sent and the ignore is set to a fractional
            # seconds value. Otherwise we can ignore it.
            
            if datetime.now() >= endtime:
                if count == 0:
                    #stash message, if it is the first one we get
                    # and it comes after the expected ignore duration
                    # but before websocket.recv() second-granularity timeout
                    # is reached
                    self.stashed_messages.append(message)
                return count
            
            count += 1 #increment ignore count

# Print iterations progress
# https://stackoverflow.com/questions/3173320/text-progress-bar-in-terminal-with-block-characters
def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end = printEnd)
    # Print New Line on Complete
    if iteration == total: 
        print()        
            
if __name__ == "__main__":
    
    messages = []
   
    with Experiment('***REMOVED***','Spinner 51 (Open Days)', user="***REMOVED***", exact=True) as expt:
        
        #receive a message to get the initial time stamp - not necessary
        expt.command('{"set":"mode","to":"stop"}')
        #time.sleep(0.05)
        expt.command('{"set":"mode","to":"position"}')
        #time.sleep(0.05)
        expt.command('{"set":"parameters","kp":1,"ki":0,"kd":0}')
        time.sleep(0.5)
        expt.command('{"set":"position","to":2}')
        # expect to throw away messages sent while sleeping ... 
        # e.g. drain(20) #helper func
        # add helper functions to extract data?
        # e.g. get 100 steps of t & d
        # needs to know about sub-arrays as well
        # and also sub keys
        # possibly gather data THEN process? to avoid variability in how much data to throw away
        # during processing breaks?
        # commands to help with data, e.g. turn off reporting, turn it back on again?
        # do we want a failure mode where data is off cos we accidentally turned it off?
        #reference the initial time stamp when figuring out how long to delay ....
        # this relies on there being timestamps in the messages, because we're accumulating a big list of messages
        # while we wait, and reading it quickly. 
        #print(websocket.ignore(timedelta(milliseconds=200)))
        expt.collect(200)
        
        # for x in range(200):
        #     message = websocket.recv()
        #     for line in message.splitlines():
        #         try:
        #             #print("<"+line+">")
        #             if line != "":
        #                 messages.append(json.loads(line))       
        #         except json.JSONDecodeError:
        #             print("oops" + line)
                    
                
    # b = Booker()
    # b.add_group("***REMOVED***")
    # b.get_bookings()
    # b.cancel_all_bookings()
    # b.get_group_details()
    # b.filter_experiments("Spin",number="51");      
    # b.book(timedelta(seconds=30)); 
    # b.get_bookings()   
    # b.get_all_activities()
    
    # qr = Queue(maxsize=10)
    # qs = Queue(maxsize=10)
    
    # url = b.connect('Spinner 51 (Open Days)')
    
    # # threading is probably going to be the easiest way to write tests
    # # BUT draining high frequency messages may be challenging?
    # messages = []
    
    # with wsconnect(url) as websocket:
        
    #    websocket.send('{"set":"mode","to":"stop"}')
    #    time.sleep(0.05)
    #    websocket.send('{"set":"mode","to":"position"}')
    #    time.sleep(0.05)
    #    websocket.send('{"set":"parameters","kp":1,"ki":0,"kd":0}')
    #    time.sleep(0.5)
    #    websocket.send('{"set":"position","to":2}')
    #    # expect to throw away messages sent while sleeping ... 
    #    # e.g. drain(20) #helper func
    #    # add helper functions to extract data?
    #    # e.g. get 100 steps of t & d
    #    # needs to know about sub-arrays as well
    #    # and also sub keys
    #    # possibly gather data THEN process? to avoid variability in how much data to throw away
    #    # during processing breaks?
    #    # commands to help with data, e.g. turn off reporting, turn it back on again?
    #    # do we want a failure mode where data is off cos we accidentally turned it off?
    #    for x in range(100):
    #        try:
    #            message = websocket.recv()
    #            messages.append(json.loads(message))       
    #        except json.JSONDecodeError:
    #            print("<<" + message + ">>")
    #            continue #typically blank lines
                      

    ts = []
    ds = []    
    for m in messages:
        try:
            for t in m["t"]:
                ts.append(t)
            for d in m["d"]:
                ds.append(d)
        except KeyError:
            continue
        
    plt.figure()        
    plt.plot(ts,ds)
        
    # #tsa = np.array(ts)
    # #dsa = np.array(ds)
    # #plt.plot(tsa/1e6,dsa)
    
        

       
            
        

           
   



                

            

        
            

        
      
            