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
    
    def filter_experiments(self, sub, number=""):
        self.filter_name = sub
        self.filter_number = number
        self.available = []
        self.unavailable = {}
        self.listed = []
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
            if activity["when"]["end"] > now:
                del self.activities[activity]
                
        ad = r.json()
        name = ad["description"]["name"]
        self.activities[name] = ad
        
    def get_all_activities(self):
        for booking in self.bookings:
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
            raise Exception("activity not found for experiment %s"%(name))
            
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
    

            
if __name__ == "__main__":
   
 
    b = Booker()
    b.add_group("***REMOVED***")
    b.get_bookings()
    b.cancel_all_bookings()
    b.get_group_details()
    b.filter_experiments("Spin",number="51");      
    b.book(timedelta(seconds=15)); 
    b.get_bookings()   
    b.get_all_activities()
    
    qr = Queue(maxsize=10)
    qs = Queue(maxsize=10)
    
    url = b.connect('Spinner 51 (Open Days)')
    
    # threading is probably going to be the easiest way to write tests
    # BUT draining high frequency messages may be challenging?
    messages = []
    
    with wsconnect(url) as websocket:
        
       #websocket.send('{"set":"mode","to":"stop"}')
       websocket.send('{"set":"mode","to":"position"}')
       websocket.send('{"set":"parameters","kp":1,"ki":0,"kd":0}')
       websocket.send('{"set":"position","to":2}')
       
       for x in range(100):
           try:
               message = websocket.recv()
               messages.append(json.loads(message))       
           except json.JSONDecodeError:
               print(message)
               continue #typically blank lines
                      

    ts = []
    ds = []    
    for m in messages:
        for t in m["t"]:
            ts.append(t)
        for d in m["d"]:
            ds.append(d)
            
    plt.figure()        
    plt.plot(ts,ds)
        
    #tsa = np.array(ts)
    #dsa = np.array(ds)
    #plt.plot(tsa/1e6,dsa)
    
        

       
            
        

           
   



                

            

        
            

        
      
            