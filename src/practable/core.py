#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 13:36:13 2024

Booker class handles logging into a booking server and making bookings
The user name is stored in the user's configuration directory, or in cwd

Experiment class handles connecting to the experiments themselves

@author: tim

"""
import collections.abc
from datetime import datetime, timedelta, timezone
import json
import math
import numpy as np
import os.path
from platformdirs import user_config_dir
from pathlib import Path
import random
import requests
import time
from urllib.parse import urlparse

from websockets.sync.client import connect as wsconnect


class Booker:

    def __init__(self,
                 book_server="https://app.practable.io/ed0/book",
                 config_in_cwd=False):

        self.book_server = book_server

        # create a configuration directory for the book_server
        # some users may use more than one booking server so keep them separate
        # config can be stored in current working directory instead, by setting
        # config_in_cwd=True when initialising; this may be helpful for
        # Jupyter notebooks

        u = urlparse(book_server)
        self.activities = {}
        self.host = u.netloc
        self.app_author = "practable"
        self.app_name = "practable-python-" + u.netloc.replace(
            ".", "-") + u.path.replace("/", "-")
        self.bookings = []
        self.groups = []
        self.group_details = {}
        self.experiments = []
        self.experiment_details = {}

        if config_in_cwd:  #for jupyter notebooks
            self.ucd = os.getcwd()
        else:
            self.ucd = user_config_dir(self.app_name, self.app_author)
            Path(self.ucd).mkdir(parents=True, exist_ok=True)

        # login to the booking system
        self.exp = datetime.now()  #set value for login expiry to trigger login
        self.ensure_logged_in()

    def __str__(self):
        if self.exp > datetime.now():
            return f"user {self.user} logged in to {self.book_server} until {self.exp}"
        else:
            return f"user {self.user} not logged in to {self.book_server}"

    def add_group(self, group):
        self.ensure_logged_in()
        url = self.book_server + "/api/v1/users/" + self.user + "/groups/" + group
        r = requests.post(url, headers=self.headers)

        if r.status_code != 204:
            print(r.status_code)
            print(r.text)
            raise Exception("could not add group %s" % (group))

        self.groups.append(group)

    def book(self, duration, selected=""):

        if not isinstance(duration, timedelta):
            raise TypeError("duration must be a datetime.timedelta")

        start = datetime.now(timezone.utc)
        end = start + duration

        if selected == "":
            # if  none specified, select an experiment from self.available
            # note: use filter_experiments to set self.available
            if len(self.available) < 1:
                if self.filter_number == "":
                    raise Exception(
                        "There are no available experiments matching `%s`" %
                        (self.filter_name))
                else:
                    raise Exception(
                        "There are no available experiments matching `%s` number `%s`"
                        % (self.filter_name, self.filter_number))

            # book a random selection from the available list
            selected = random.choice(self.available)

        # make the booking
        slot = self.experiment_details[selected]["slot"]
        url = self.book_server + "/api/v1/slots/" + slot
        params = {
            "user_name": self.user,
            "from": start.isoformat(),
            "to": end.isoformat(),
        }

        r = requests.post(url, params=params, headers=self.headers)

        if r.status_code != 204:
            print(r.status_code)
            print(r.text)
            raise Exception("could not book %s for %s" % (selected, duration))

    def cancel_booking(self, name):

        url = self.book_server + "/api/v1/users/" + self.user + "/bookings/" + name

        r = requests.delete(url, headers=self.headers)

        if r.status_code != 404:
            print(r.status_code)
            print(r.text)
            raise Exception("could not cancel booking %s" % (name))

    def cancel_all_bookings(self):

        self.get_bookings()  #refresh current bookings

        for booking in self.bookings:
            try:
                self.cancel_booking(booking["name"])
            except:
                pass  #ignore the case where we get 500 can't cancel booking that already ended

        self.get_bookings()

        if len(self.bookings) > 0:
            raise Exception("unable to cancel all bookings")

    def check_slot_available(self, slot):
        url = self.book_server + "/api/v1/slots/" + slot
        r = requests.get(url, headers=self.headers)
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not get slot details for slot %s" % (slot))

        avail = r.json()
        if len(avail) < 1:
            available_now = False
            when = []
        else:
            start = datetime.fromisoformat(avail[0]["start"])
            end = datetime.fromisoformat(avail[0]["end"])
            when = {"start": start, "end": end}
            available_now = when["start"] <= (datetime.now(timezone.utc) +
                                              timedelta(seconds=1))

        return available_now, when

    def ensure_logged_in(
            self):  #most booking operations take much less than a minute

        if not self.exp > (datetime.now() + timedelta(minutes=2)):

            self.ensure_user()

            r = requests.post(self.book_server + "/api/v1/login/" + self.user)

            if r.status_code != 200:
                print(r.status_code)
                print(r.text)
                raise Exception("could not login as user %s at %s" %
                                (self.user, self.booking_server))

            rj = r.json()
            self.exp = datetime.fromtimestamp(rj["exp"])
            self.headers = {
                'Content-Type': 'application/json',
                'Authorization': '{}'.format(rj['token'])
            }

    def ensure_user(self):
        # check if we have previously stored a user name in config dir
        try:
            f = open(os.path.join(self.ucd, 'user'))
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
            raise Exception("could not get new user id from %s" %
                            (self.book_server))
        user = r.json()["user_name"]
        with open(os.path.join(self.ucd, 'user'), 'w') as file:
            file.write(user)
        self.user = user

    def set_user(self, user):

        with open(os.path.join(self.ucd, 'user'), 'w') as file:
            file.write(user)
        self.user = user

    def filter_experiments(self, sub, number="", exact=False):
        self.filter_name = sub
        self.filter_number = number
        self.available = []
        self.unavailable = {}
        self.listed = []

        if exact == True and sub in self.experiments:
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
            available_now, when = self.check_slot_available(
                self.experiment_details[name]["slot"])
            if available_now:
                self.available.append(name)
            else:
                self.unavailable[name] = when["start"]

    def get_activity(self, booking):
        #get the activity associated with a booking (use the uuid in the name field)
        url = self.book_server + "/api/v1/users/" + self.user + "/bookings/" + booking
        r = requests.put(url, headers=self.headers)
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not get activity for booking %s" %
                            (booking))

        #remove stale activities
        activities = self.activities
        now = datetime.now(timezone.UTC)
        for activity in activities:
            if datetime.fromtimestamp(activity["exp"], tz=timezone.utc) > now:
                del self.activities[activity]

        ad = r.json()
        # we can only link an activity with a booking at the time we request it
        # so we need to store that link in the activity to allow cancellation
        # cancelling all bookings will interfere with other instances operating
        # on the same machine
        ad["booking"] = booking  #so we can identify which booking to cancel

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
            raise Exception("could not get bookings for %s from %s" %
                            (self.user, self.booking_server))

        bookings = r.json()

        now = datetime.now(timezone.utc)

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
                raise Exception("could not get group details for group %s" %
                                (group))

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
                if s["for"] == which:
                    stream = s
        except KeyError:
            raise KeyError("activity not found for experiment %s" % (name))

        if stream == {}:
            raise Exception("stream %s not found" % (which))

        url = stream["url"]
        token = stream["token"]
        headers = {
            'Content-Type': 'application/json',
            'Authorization': '{}'.format(token)
        }

        r = requests.post(url, headers=headers)
        if r.status_code != 200:
            print(r.status_code)
            print(r.text)
            raise Exception("could not access %s stream %s" % (which, name))

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
    # Note: we handle keys search syntax ourselves, rather than use jq, because jupyter notebooks won't have jq installed
    # and the python module is just a wrapper to that executable, not an actual re-implementation of it.
    def __init__(self,
                 group,
                 name,
                 user="",
                 book_server="",
                 config_in_cwd=False,
                 duration=timedelta(minutes=3),
                 exact=False,
                 number="",
                 time_format="ms",
                 time_key="t",
                 key_separator="/",
                 cancel_new_booking_on_exit=True,
                 max_wait_to_start=timedelta(minutes=1)):

        if book_server == "":
            self.booker = Booker(
                config_in_cwd=config_in_cwd)  #use the default booking server
        else:
            self.booker = Booker(book_server=book_server,
                                 config_in_cwd=config_in_cwd)

        self.duration = duration
        self.exact = exact
        self.group = group
        self.key_separator = key_separator
        self.name = name
        self.number = number
        self.stashed_messages = []
        self.time_format = time_format
        self.time_key = time_key
        self.user = user
        self.cancel_new_booking_on_exit = cancel_new_booking_on_exit

    def __enter__(self):
        # set a specific user, e.g. online identity used to book the kit already
        # i.e. a booking we want to use interactively without cancelling it
        if self.user != "":
            self.booker.set_user(self.user)

        self.booker.add_group(self.group)
        # see if we have an existing booking
        self.booker.get_bookings()
        self.booker.get_all_activities()

        try:
            self.url = self.booker.connect(self.name)
            self.cancel_booking_on_exit = False
        except KeyError:
            # make a booking
            self.booker.get_group_details()
            self.booker.filter_experiments(self.name, self.number, self.exact)
            self.booker.book(self.duration)
            self.booker.get_bookings()
            self.booker.get_all_activities()
            self.url = self.booker.connect(self.name)
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

    def collect_count(self, count, timeout=None, verbose=True):
        messages = []
        collected = 0

        while collected < count:
            try:
                # getg next stashed message
                message = self.stashed_messages.pop(0)
                messages.append(message)
                collected += 1

            except IndexError:  # no stashed messages
                message = self.recv(timeout=timeout)
                #print("recevied message: " + message)

                for line in message.splitlines():
                    try:
                        if line != "":
                            obj = json.loads(line)

                            if collected < count:
                                messages.append(obj)
                                collected += 1
                            else:
                                # got too many messages at once, now exceeded count
                                # so stash messages not needed
                                self.stashed_messages.append(obj)
                    except json.JSONDecodeError:
                        print("Warning could not decode as JSON:" + line)
            if verbose:
                printProgressBar(collected,
                                 count,
                                 prefix=f'Collecting {count} messages',
                                 suffix='Complete',
                                 length=50)

        if verbose:
            print(
                end="\n"
            )  #make sure next message does not overwrite completed progress bar

        return messages

    def command(self, message, verbose=True):
        if verbose:
            print("Command: " + message)
        self.send(message)

    def extract(self, obj, key, separator="/"):

        # Extract a key:value pair from an object
        # The specified key may be several levels down in the object
        # For example, we may need to find time values
        # These may not be at the top level of the object
        # e.g. key="data/time" means we're returning message["data"]["time"]

        keys = key.split(separator)

        if len(keys) == 0:
            return None

        v = obj
        try:
            for k in keys:
                v = v[k]
                return v
        except KeyError:
            raise KeyError("time key not found in this message")

    def extract_series(self, arr, key, separator="/"):
        values = []
        for obj in arr:
            vv = self.extract(obj, key, separator=separator)
            for v in vv:
                values.append(v)
        return values

    def recv(self, timeout=None):
        return self.websocket.recv(timeout=timeout)

    def send(self, message):
        self.websocket.send(message)
        time.sleep(0.05)  #rate limiting step to ensure messages are separate

    def ignore(self, duration_seconds, timeout=None, verbose=True):
        return self.collect_duration(duration_seconds,
                                     timeout=None,
                                     verbose=True,
                                     ignore=True)

    def collect(self, duration_seconds, timeout=None, verbose=True):
        return self.collect_duration(duration_seconds,
                                     timeout=None,
                                     verbose=True,
                                     ignore=False)

    def collect_duration(self,
                         duration_seconds,
                         timeout=None,
                         verbose=True,
                         ignore=False):
        # implementation of collect() and ignore()
        # select ignore=True for ignore()
        # duration is a float, to make interface easier to type/understand for new users
        # e.g.
        # collect(0.5)  vs
        # collect(timedelta(milliseconds=500))
        collected = []

        mode = "Collecting"
        if ignore:
            mode = "Ignoring"

        duration = timedelta(seconds=duration_seconds)

        if self.time_format != "ms":
            raise KeyError(
                f"Unknown time_format {self.time_format}, valid options are: ms"
            )

        while True:

            messages = self.collect_count(1, timeout=timeout, verbose=False)
            # the value is either a single time value, or an array of them
            # we exclude handling arrays of sub-objects each containing a time-stamp
            # because this complicates the filter implementation

            if not ignore:
                for message in messages:
                    collected.append(message)

            try:
                times = self.extract(messages[0],
                                     self.time_key,
                                     separator=self.key_separator)
                break
            except KeyError:
                continue

        t0 = timedelta()

        if self.time_format == "ms":
            if isinstance(times, (collections.abc.Sequence,
                                  np.ndarray)) and not isinstance(times, str):
                t0 = timedelta(milliseconds=times[0])
            else:
                t0 = timedelta(milliseconds=times)
        else:
            raise Exception("time_format not implemented")

        t1 = t0 + duration  #the time we're waiting for, in the messages

        # we're tracking two different forms of time here
        # the time in the messages, if we are getting them
        # and the time that has passed on our own clock, if we're not
        # we need to stop ignoring if there are no messages in the given time

        endtime = datetime.now() + duration

        #timeout is in seconds, so round up to nearest whole seconds
        # if this is longer than we want to wait, no worries, because
        # it only times out if there was no data anyway.
        timeout = math.ceil(duration.total_seconds())

        count = 0

        while True:

            try:
                messages = self.collect_count(1,
                                              timeout=timeout,
                                              verbose=False)

            except TimeoutError:
                # timed out, so return
                return collected

            # check for edge case for ignore, which is that:
            # if no message is received while we are ignoring
            # but then we get one after the ignore duration has expired
            # but before the timeout we created with whole number
            # seconds has expired (e.g. a message at 700ms on a 500ms ignore,
            # which requires a 1s timeout) then
            # we have to stash it to be received by user
            # in case there are sparsely/unevenly spaced but important
            # messages being sent and the ignore is set to a fractional
            # seconds value. Otherwise we can ignore it.

            if ignore and datetime.now() >= endtime:
                if count == 0:
                    #stash message, if it is the first one we get
                    # and it comes after the expected ignore duration
                    # but before websocket.recv() second-granularity timeout
                    # is reached
                    for message in messages:
                        self.stashed_messages.append(message)
                return collected

            if not ignore:
                for message in messages:
                    collected.append(message)
            count += len(messages)  #increment ignore count

            # check if the time in the message has reached the time we are
            # waiting for, t1

            #want the last message, as that is the most recent
            try:
                times = self.extract(messages[-1],
                                     self.time_key,
                                     separator=self.key_separator)
            except KeyError:
                continue  #no times in this message, so keep checking

            t1 = timedelta()

            if self.time_format == "ms":
                if isinstance(times,
                              (collections.abc.Sequence,
                               np.ndarray)) and not isinstance(times, str):
                    t1 = timedelta(milliseconds=times[-1])
                else:
                    t1 = timedelta(milliseconds=times)
            else:
                raise Exception("time_format not implemented")

            if verbose:
                # progress bar tends to overshoot, because there are multiple timestamps per message
                # Ignoring messages for 1.0 seconds |██████████████████████████████████████████████████| 101.8% Complete
                # let's hide that under the rug for now, to be easier for new users

                amount = (t1 - t0).total_seconds()
                total = duration.total_seconds()
                if amount > total:
                    amount = total
                printProgressBar(
                    amount,
                    total,
                    prefix=
                    f'{mode} messages for {duration.total_seconds()} seconds',
                    suffix='Complete',
                    length=50)
            if (t1 - t0) > duration:
                print(
                    end="\n"
                )  #ensure next line does not overwrite our finished progress bar
                return collected


# Print iterations progress
# https://stackoverflow.com/questions/3173320/text-progress-bar-in-terminal-with-block-characters
def printProgressBar(iteration,
                     total,
                     prefix='',
                     suffix='',
                     decimals=1,
                     length=100,
                     fill='█',
                     printEnd="\r"):
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
    percent = ("{0:." + str(decimals) + "f}").format(
        100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end=printEnd)
    # Print New Line on Complete
    if iteration == total:
        print()


if __name__ == "__main__":

    print("""
#Example code:
%pip install practable    
import matplotlib.pyplot as plt
from practable.core import Experiment

messages = []
   
#modify with actual group code and experiment name
with Experiment('g-open-xxxxx','Spinner 51', exact=True) as expt:
    
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
    plt.legend()""")
