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
from platformdirs import *
from pathlib import Path
import requests

app_author = "practable" 
app_name = "practable-python"

ucd = user_config_dir(app_name, app_author)
udd = user_config_dir(app_name, app_author)

default_book_server = "https://app.practable.io/ed0/book"

def idempotent_setup():
    Path(ucd).mkdir(parents=True, exist_ok=True)
    Path(udd).mkdir(parents=True, exist_ok=True)   
    
def set_book_server(url):
    idempotent_setup()
    with open(os.path.join(ucd,'book_server'), 'w') as file:
        file.write(url)

def get_book_server():
    idempotent_setup()
    try:
        f = open(os.path.join(ucd,'book_server'))
        book_server = f.readline()
        return book_server
    except FileNotFoundError:
        # set default
        idempotent_setup()
        #raise Warning('no config file found, using default book server')
        with open(os.path.join(ucd,'book_server'), 'w') as file:
            file.write(default_book_server)
        return default_book_server
                            
def get_user():
    idempotent_setup()
    try:
        f = open(os.path.join(ucd,'user'))
        user = f.readline()
        if user != "":
            return user
            
    except FileNotFoundError:
        pass
    
    #if get to here, user is not found, or empty, so get a new one
    target = get_book_server() + "/api/v1/users/unique"
    r = requests.post(target)
    if r.status_code != 200:
        print(r.status_code)
        print(r.text)
        raise Exception("could not get new user id from %s"%(target))
    user = r.json()["user_name"]    
    with open(os.path.join(ucd,'user'), 'w') as file:
        file.write(user)
    return user
    
    
    
