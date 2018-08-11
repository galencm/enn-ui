# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2018, Galen Curwen-McAdams

import argparse
import atexit
import threading
import time
import attr
import redis
from lxml import etree
import keli.slurp_gphoto2 as sg
import pyudev
import os
from ma_cli import data_models

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button

r_ip, r_port = data_models.service_connection()
binary_r = redis.StrictRedis(host=r_ip, port=r_port)
redis_conn = redis.StrictRedis(host=r_ip, port=r_port, decode_responses=True)

@attr.s
class Device(object):
    connected = attr.ib(default=False)
    details = attr.ib(default=attr.Factory(dict))

class DeviceItem(BoxLayout):
    def __init__(self, *args, **kwargs):
        self.device = Device()
        super(DeviceItem, self).__init__()
        self.details_container = BoxLayout(orientation="vertical")
        self.add_widget(self.details_container)

    def update_details(self):
        self.details_container.clear_widgets()
        connected_color = [.5, .5, .5, 1]
        if self.device.connected:
            connected_color = [0, 1, 0, 1]
        self.details_container.add_widget(Button(background_color=connected_color, height=30, size_hint_y=None))
        for k, v in self.device.details.items():
            row = BoxLayout(height=30, size_hint_y=None)
            key = Label(text=str(k))
            value = Label(text=str(v))
            row.add_widget(key)
            row.add_widget(value)
            self.details_container.add_widget(row)

class DevApp(App):
    def __init__(self, *args, **kwargs):
        # store kwargs to passthrough
        self.kwargs = kwargs
        if kwargs["db_host"] and kwargs["db_port"]:
            global binary_r
            global redis_conn
            db_settings = {"host" :  kwargs["db_host"], "port" : kwargs["db_port"]}
            binary_r = redis.StrictRedis(**db_settings)
            redis_conn = redis.StrictRedis(**db_settings, decode_responses=True)

        self.db_port = redis_conn.connection_pool.connection_kwargs["port"]
        self.db_host = redis_conn.connection_pool.connection_kwargs["host"]
        self.env_key = "machinic:env:{}:{}".format(self.db_host, self.db_port)
        self.session_save_path = "~/.config/enn-ui/"
        self.session_save_filename = "session_{}_{}.xml".format(self.db_host, self.db_port)

        super(DevApp, self).__init__()

    def build(self):
        root = BoxLayout()
        self.device_container = BoxLayout()
        root.add_widget(self.device_container)
        self.update_env_values()
        self.load_session()
        # classes for device discovery and interaction
        # .discover() is called for discovery
        self.device_classes = {}
        self.device_classes["gphoto2"] = sg.SlurpGphoto2(binary_r=binary_r, redis_conn=redis_conn)

        self.db_event_subscription = redis_conn.pubsub()
        self.db_event_subscription.psubscribe(**{'__keyspace@0__:*': self.handle_db_events})
        # add thread to pubsub object to stop() on exit
        self.db_event_subscription.thread = self.db_event_subscription.run_in_thread(sleep_time=0.001)
        # monitor usb events to show local device connect / disconnect
        # there may be other sources that are accessible over the 
        # db or network
        usb_event_thread = threading.Thread(target=self.usb_events)
        # end thread when window is closed
        usb_event_thread.daemon = True
        usb_event_thread.start()
        self.update_devices()
        return root

    def usb_events(self):
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)

        def log_event(action, device):
            print("action: {} device: {}".format(action, device))
            if action in ("add", "remove"):
                Clock.schedule_once(lambda dt: self.update_devices(), .01)

        observer = pyudev.MonitorObserver(monitor, log_event)
        observer.start()
        # loop since this will be run in a thread
        while True:
            time.sleep(0.1)

    def update_devices(self):
        discovered = []
        for name, device_class in self.device_classes.items():
            discovered.extend(device_class.discover())

        # reset existing device connected status
        # before rediscovery / nondiscovery
        for child in self.device_container.children:
            child.device.connected = False
            child.update_details()

        for device in discovered:
            if not device["uid"] in [child.device.details["uid"] for child in self.device_container.children]:
                device_widget = DeviceItem()
                device_widget.device.details = device
                device_widget.device.connected = True
                device_widget.update_details()
                self.device_container.add_widget(device_widget)
            else:
                for child in self.device_container.children:
                    if device["uid"]  == child.device.details["uid"]:
                        child.device.connected = True
                        child.update_details()

    def update_env_values(self):
        env_values = redis_conn.hgetall(self.env_key)

    def handle_db_events(self, message):
        msg = message["channel"].replace("__keyspace@0__:","")
        if msg in (self.env_key):
            Clock.schedule_once(lambda dt: self.update_env_values(), .1)

    def load_session(self):
        expanded_path = os.path.expanduser(self.session_save_path)
        file = os.path.join(expanded_path, self.session_save_filename)
        xml = etree.parse(file)
        for session in xml.xpath('//session'):
            for device in session.xpath('//device'):
                device_widget = DeviceItem()
                device_widget.device.details = device.attrib
                device_widget.update_details()
                self.device_container.add_widget(device_widget)

    def save_session(self):
        expanded_path = os.path.expanduser(self.session_save_path)
        if not os.path.isdir(expanded_path):
            print("creating: {}".format(expanded_path))
            os.mkdir(expanded_path)

        machine = etree.Element("machine")
        session = etree.Element("session")
        machine.append(session)

        # store devices so unfound will show up
        # on restart
        for device in [child.device for child in self.device_container.children]:
            dev =  etree.Element("device")
            for k, v in device.details.items():
                dev.set(k, v)
            session.append(dev)
        machine_root = etree.ElementTree(machine)

        if os.path.isfile(os.path.join(expanded_path, self.session_save_filename)):
            os.remove(os.path.join(expanded_path, self.session_save_filename))

        machine_root.write(os.path.join(expanded_path, self.session_save_filename), pretty_print=True)

    def on_stop(self):
        # stop pubsub thread if window closed with '[x]'
        self.db_event_subscription.thread.stop()

    def app_exit(self):
        self.db_event_subscription.thread.stop()
        App.get_running_app().stop()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-key",  help="db hash key")
    parser.add_argument("--db-key-field",  help="db hash field")

    parser.add_argument("--db-host",  help="db host ip, requires use of --db-port")
    parser.add_argument("--db-port", type=int, help="db port, requires use of --db-host")
    args = parser.parse_args()

    if bool(args.db_host) != bool(args.db_port):
        parser.error("--db-host and --db-port values are both required")

    app = DevApp(**vars(args))
    atexit.register(app.save_session)
    app.run()
