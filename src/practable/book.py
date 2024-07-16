#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 13:36:13 2024

Booker class handles logging into a booking server and making bookings
The user name is stored in the user's configuration directory, or in cwd

@author: tim

"""
from datetime import datetime, timedelta, UTC
import os.path
from platformdirs import user_config_dir
from pathlib import Path
import random
import requests
from urllib.parse import urlparse


class Booker:
    
    def __init__(self, book_server="https://app.practable.io/ed0/book", config_in_cwd=False):

        self.book_server = book_server
        
        # create a configuration directory for the book_server
        # some users may use more than one booking server so keep them separate
        # config can be stored in current working directory instead, by setting 
        # config_in_cwd=True when initialising; this may be helpful for
        # Jupyter notebooks
        
        u = urlparse(book_server)
        self.host = u.netloc
        self.app_author = "practable" 
        self.app_name = "practable-python-" + u.netloc.replace(".","-") + u.path.replace("/","-")
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
    
    def get_bookings(self):
        self.ensure_logged_in()
        url = self.book_server + "/api/v1/users/" + self.user + "/bookings"
        r = requests.get(url, headers=self.headers)      
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not get bookings for %s from %s"%(self.user, self.booking_server)) 
            
        self.bookings = r.json()

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
                
    def book(self, duration):
        
        if not isinstance(duration, timedelta):
            raise TypeError("duration must be a datetime.timedelta")

        start =  datetime.now(UTC)
        end = start + duration
        
        if len(self.available) < 1:
            if self.filter_number == "":
                raise Exception("There are no available experiments matching `%s`"%(self.filter_name))            
            else:
                raise Exception("There are no available experiments matching `%s` number `%s`"%(self.filter_name,self.filter_number))  
                
        # book a random selection from the available list
        selected = random.choice(self.available)
                
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
            raise Exception("could not booking %s for %s"%(selected, duration))    
      
            