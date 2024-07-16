#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 13:36:13 2024

Uses configuration files as follows:
user_config_dir/user for the user name
user_config_dir/book_server for the book server (will use a default if none found)

@author: tim

"""

import os.path
from platformdirs import user_config_dir
from pathlib import Path
import requests
from datetime import datetime
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
        
        if config_in_cwd: #for jupyter notebooks
            self.ucd = os.getcwd()
        else:
            self.ucd = user_config_dir(self.app_name, self.app_author)
            Path(self.ucd).mkdir(parents=True, exist_ok=True)

        # get the user name (needed to login and make bookings)
        self.get_user()
        self.login()
        
    def __str__(self):
        if self.exp > datetime.now():
            return f"user {self.user} logged in to {self.book_server} until {self.exp}"
        else:
            return f"user {self.user} not logged in to {self.book_server}"
    
     
    def login(self):
           
        r = requests.post(self.book_server + "/api/v1/login/" + self.user)
        
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not login as user %s at %s"%(self.user, self.booking_server))

        rj = r.json()
        self.token = rj["token"]
        self.exp = datetime.fromtimestamp(rj["exp"]) 
    
    def ensure_logged_in(self):
        if not self.exp > datetime.now():
            self.login()
        
    def add_group(self,group):
        self.ensure_logged_in()        
   
    def get_user(self):
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
    

