# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2018, Galen Curwen-McAdams

import argparse
import atexit
import threading
import subprocess
import time
import attr
import redis
from lxml import etree
import keli.slurp_gphoto2 as sg
import pyudev
import os
from ma_cli import data_models
import fold_ui.keyling as keyling

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.animation import Animation
from kivy.uix.scrollview import ScrollView

r_ip, r_port = data_models.service_connection()
binary_r = redis.StrictRedis(host=r_ip, port=r_port)
redis_conn = redis.StrictRedis(host=r_ip, port=r_port, decode_responses=True)


@attr.s
class Device(object):
    connected = attr.ib(default=False)
    details = attr.ib(default=attr.Factory(dict))
    settings = attr.ib(default=attr.Factory(dict))

    def settings_prefixed(self, prefix):
        settings = {}
        # include scripts
        settings["{}{}".format(prefix, "scripts")] = self.details["scripts"]
        for k, v in self.settings.items():
            settings["{}{}".format(prefix, k)] = v
        return settings


@attr.s
class Conditional(object):
    name = attr.ib(default="")
    device = attr.ib(default="")
    pre_contents = attr.ib(default=attr.Factory(list))
    set_contents = attr.ib(default=attr.Factory(dict))
    post_contents = attr.ib(default=attr.Factory(list))
    # device may or may not be included in keyname
    # settings:pre:foo:<device?>:127.0.0.1:6379 #list of keyling scripts
    # settings:set:foo:<device?>:127.0.0.1:6379 #hash of key:values to set
    # settings:post:foo:<device?>:127.0.0.1:6379 #list of keyling scripts

    def keys(self, remove_only=False):
        db_port = redis_conn.connection_pool.connection_kwargs["port"]
        db_host = redis_conn.connection_pool.connection_kwargs["host"]
        self.key_template = "settings:{step}:{name}:{device}:{host}:{port}"
        template_values = {
            "name": self.name,
            "device": self.device,
            "host": db_host,
            "port": db_port,
        }
        for step in ["pre", "set", "post"]:
            template_values.update({"step": step})
            key_name = self.key_template.format_map(template_values)
            contents = getattr(self, step + "_contents")
            redis_conn.delete(key_name)
            if not remove_only:
                if isinstance(contents, list):
                    # only write nonempty values
                    if contents:
                        try:
                            redis_conn.lpush(key_name, *contents)
                        except Exception as ex:
                            print(ex)
                elif isinstance(contents, dict):
                    # only write nonempty values
                    if contents:
                        try:
                            redis_conn.hmset(key_name, contents)
                        except Exception as ex:
                            print(ex)


class ConditionItem(BoxLayout):
    def __init__(self, *args, parent_device=None, **kwargs):
        self.orientation = "vertical"
        self.parent_device = parent_device
        self.height = 300
        self.size_hint_y = None
        super(ConditionItem, self).__init__()
        self.conditional = Conditional()
        self.top_container = BoxLayout(size_hint_y=1)
        self.env_container = BoxLayout(orientation="vertical")
        self.set_container = BoxLayout(orientation="vertical")
        self.post_container = BoxLayout(
            orientation="vertical", size_hint_y=None, height=60
        )
        self.top_container.add_widget(self.env_container)
        self.top_container.add_widget(self.set_container)
        self.name_input = TextInput(
            hint_text="name", multiline=False, height=30, size_hint_y=None
        )
        self.name_input.bind(
            on_text_validate=lambda widget: setattr(
                self.conditional, "name", widget.text
            )
        )
        self.add_widget(self.name_input)
        self.add_widget(self.top_container)
        self.add_widget(self.post_container)
        store_button = Button(text="store", height=30, size_hint_y=None)
        store_button.bind(on_press=lambda widget: self.store())
        self.add_widget(store_button)
        remove_button = Button(text="remove", height=30, size_hint_y=None)
        remove_button.bind(
            on_press=lambda widget: [
                self.conditional.keys(remove_only=True),
                self.parent.remove_widget(self),
            ]
        )

        self.add_widget(remove_button)
        self.update()

    def update_from_conditional(self):
        self.name_input.text = str(self.conditional.name)
        self.env_input.text = ""
        if self.conditional.pre_contents:
            self.env_input.text = self.conditional.pre_contents[0]

        self.set_input.text = ""
        for k, v in self.conditional.set_contents.items():
            self.set_input.text += "{} = {}\n".format(k, v)
        self.post_input.text = ""
        if self.conditional.post_contents:
            self.post_input.text = self.conditional.post_contents[0]

    def update(self):
        self.env_container.clear_widgets()
        self.set_container.clear_widgets()
        self.env_input = TextInput(hint_text="add conditions (keyling)")
        self.set_input = TextInput(
            hint_text="add settings (newline delimited 'foo = bar')"
        )
        self.post_input = TextInput(hint_text="add post calls (keyling)")
        # on_validate does not call for multiline
        # env_input.bind(on_text_validate=lambda widget: self.validate_keyling(widget.text, widget))
        # set_input.bind(on_text_validate=lambda widget: self.validate_setting(widget.text, widget))
        # post_input.bind(on_text_validate=lambda widget: self.validate_keyling(widget.text, widget))
        self.env_container.add_widget(self.env_input)
        self.set_container.add_widget(self.set_input)
        preview_button = Button(text="preview", height=30, size_hint_y=None)
        preview_button.bind(
            on_press=lambda widget: self.parent_device.preview(
                settings=self.validate_setting(self.set_input.text)
            )
        )
        self.set_container.add_widget(preview_button)
        self.post_container.add_widget(self.post_input)

    def store(self):
        self.validate_keyling(
            self.env_input.text, set_on_valid="pre_contents", widget=self.env_input
        )
        self.validate_setting(
            self.set_input.text, set_on_valid="set_contents", widget=self.set_input
        )
        self.validate_keyling(
            self.post_input.text, set_on_valid="post_contents", widget=self.post_input
        )
        self.conditional.keys()

    def validate_keyling(self, text, set_on_valid=None, widget=None):
        current_background = [1, 1, 1, 1]
        try:
            # validate model
            keyling.model(text)
            if widget:
                anim = Animation(
                    background_color=[0, 1, 0, 1], duration=0.5
                ) + Animation(background_color=current_background, duration=0.5)
                anim.start(widget)
            if set_on_valid:
                setattr(self.conditional, set_on_valid, [text])
        except Exception as ex:
            if widget:
                anim = Animation(
                    background_color=[1, 0, 0, 1], duration=0.5
                ) + Animation(background_color=current_background, duration=0.5)
                anim.start(widget)

    def validate_setting(self, text, set_on_valid=None, widget=None):
        # simple parsing for
        # key = value newline delimited
        text = text.strip()
        settings = {}
        current_background = [1, 1, 1, 1]
        valid = False
        for line in text.split("\n"):
            line = line.strip()
            try:
                key, value = line.split("=")
                key = key.strip()
                value = value.strip()
                valid = True
                settings[key] = value
            except Exception as ex:
                valid = False

        if valid:
            if widget:
                anim = Animation(
                    background_color=[0, 1, 0, 1], duration=0.5
                ) + Animation(background_color=current_background, duration=0.5)
                anim.start(widget)
            if set_on_valid:
                setattr(self.conditional, set_on_valid, settings)
            return settings
        else:
            if widget:
                anim = Animation(
                    background_color=[1, 0, 0, 1], duration=0.5
                ) + Animation(background_color=current_background, duration=0.5)
                anim.start(widget)


class DeviceItem(BoxLayout):
    def __init__(self, *args, app=None, **kwargs):
        self.orientation = "vertical"
        self.device = Device()
        self.app = app
        # by default open previewed with dzz
        self.default_view_call = "dzz-ui --size=1500x900 -- --db-host {host} --db-port {port} --db-key {thing} --db-key-field {thing_field}"
        self.state_key_template = "device:state:{uid}"
        self.setting_prefix = "SETTING_"
        super(DeviceItem, self).__init__()
        self.details_container = BoxLayout(orientation="vertical")
        self.conditions_container = BoxLayout(
            orientation="vertical", size_hint_y=None, height=1000, minimum_height=200
        )
        self.conditions_frame = BoxLayout(orientation="horizontal")
        self.settings_widgets = []
        self.conditional_widgets = []
        self.add_widget(self.details_container)
        create_condition_button = Button(text="new\ncond", width=60, size_hint_x=None)
        create_condition_button.bind(on_press=lambda widget: self.add_conditional())
        self.conditions_frame.add_widget(create_condition_button)
        conditions_scroll = ScrollView(bar_width=20)
        conditions_scroll.add_widget(self.conditions_container)

        self.conditions_frame.add_widget(conditions_scroll)
        self.add_widget(self.conditions_frame)

    def update_conditions(self):
        self.conditions_container.clear_widgets()
        db_port = redis_conn.connection_pool.connection_kwargs["port"]
        db_host = redis_conn.connection_pool.connection_kwargs["host"]
        key_template = "settings:{step}:{name}:{device}:{host}:{port}"
        template_values = {
            "name": "*",
            "device": self.device.details["uid"],
            "host": db_host,
            "port": db_port,
        }

        found = {}
        for step in ["pre", "set", "post"]:
            template_values.update({"step": step})
            pattern = key_template.format_map(template_values)
            print(pattern)
            for found_keys in redis_conn.scan_iter(match=pattern):
                _, _, name, uid, _, _ = found_keys.split(":")
                if name not in found:
                    found[name] = {}
                found[name][step] = found_keys

        for conditional_name, step in found.items():
            c = ConditionItem()
            c.conditional.device = self.device.details["uid"]
            c.parent_device = self
            c.conditional.name = conditional_name
            for step_name, step_key in step.items():
                contents = None
                try:
                    contents = redis_conn.lrange(step_key, 0, -1)
                except Exception as ex:
                    try:
                        contents = redis_conn.hgetall(step_key)
                    except Exception as ex:
                        pass
                if contents:
                    setattr(c.conditional, "{}_contents".format(step_name), contents)

            c.update_from_conditional()
            self.add_conditional(c)

    def add_conditional(self, conditional=None):
        if conditional is None:
            conditional = ConditionItem()
            conditional.conditional.device = self.device.details["uid"]
            conditional.parent_device = self
        self.conditions_container.add_widget(conditional)
        self.conditions_container.parent.scroll_to(conditional)
        self.conditions_container.height += conditional.height

    def update_details(self):
        self.details_container.clear_widgets()
        self.settings_widgets = []
        connected_color = [.5, .5, .5, 1]
        connected_text = "not connected"
        if self.device.connected:
            connected_color = [0, 1, 0, 1]
            connected_text = "connected"
        status_row = BoxLayout()
        connected_button = Button(
            text=connected_text,
            background_color=connected_color,
            height=30,
            size_hint_y=None,
        )
        connected_button.bind(on_press=lambda widget: self.app.update_devices())
        remove_button = Button(text="clear", height=30, size_hint_y=None)
        remove_button.bind(on_press=lambda widget: [self.parent.remove_widget(self)])
        status_row.add_widget(connected_button)
        status_row.add_widget(remove_button)
        self.details_container.add_widget(status_row)

        # device information
        for k, v in self.device.details.items():
            row = BoxLayout(height=30, size_hint_y=None)
            key = Label(text=str(k))
            value = Label(text=str(v))
            row.add_widget(key)
            row.add_widget(value)
            self.details_container.add_widget(row)

        # add adjustable values from the db
        # the db material is generated from xml
        # see enn-db and reference.xml
        try:
            # incorrect keys will be stored/reloaded from xml
            if "scripts" not in self.device.details:
                self.device.details["scripts"] = redis_conn.hget(
                    "device:script_lookup", self.device.details["name"]
                )

            reference = redis_conn.hgetall(
                "scripts:{}".format(self.device.details["scripts"])
            )
            for attribute, _ in reference.items():
                row = BoxLayout(height=30, size_hint_y=None)
                key = Label(text=str(attribute))
                value = TextInput(multiline=False)
                try:
                    value.text = self.device.settings[attribute]
                except KeyError as ex:
                    print(ex)
                    pass
                value.bind(
                    on_text_validate=lambda widget, attribute=attribute: self.set_device_setting(
                        attribute, widget.text, widget
                    )
                )
                # store to get set_device_setting before preview
                value.attribute = attribute
                self.settings_widgets.append(value)
                row.add_widget(key)
                row.add_widget(value)
                self.details_container.add_widget(row)
        except Exception as ex:
            print(ex)

        # preview
        self.view_call_input = TextInput(
            text=self.default_view_call, multiline=False, height=30, size_hint_y=None
        )
        self.view_call_input.bind(on_text_validate=lambda widget: self.check_call())
        preview_button = Button(
            text="preview",
            background_color=connected_color,
            height=60,
            size_hint_y=None,
        )
        preview_button.bind(on_press=lambda widget: self.preview())

        get_state_button = Button(text="get state", height=30, size_hint_y=None)
        set_state_button = Button(text="set state", height=30, size_hint_y=None)
        get_state_button.bind(on_press=lambda widget: self.get_state())
        set_state_button.bind(on_press=lambda widget: self.set_state())
        get_set_state_row = BoxLayout(height=30, size_hint_y=None)
        load_state_from_row = BoxLayout(height=30, size_hint_y=None)
        load_state_from_button = Button(
            text="load state from", height=30, size_hint_y=None
        )
        load_state_from_input = TextInput(
            hint_text="db key", multiline=False, height=30, size_hint_y=None
        )
        load_state_from_button.bind(
            on_press=lambda widget, state_source=load_state_from_input: self.load_state(
                load_state_from_input.text
            )
        )
        get_set_state_row.add_widget(get_state_button)
        get_set_state_row.add_widget(set_state_button)
        self.details_container.add_widget(get_set_state_row)
        load_state_from_row.add_widget(load_state_from_button)
        load_state_from_row.add_widget(load_state_from_input)
        self.details_container.add_widget(load_state_from_row)
        self.details_container.add_widget(self.view_call_input)
        self.details_container.add_widget(preview_button)
        self.update_conditions()

    def get_state(self):
        state = redis_conn.hgetall(
            self.state_key_template.format_map(self.device.details)
        )
        if state:
            self.device.settings = state
        else:
            self.device.settings = {}
        self.update_details()

    def set_state(self):
        redis_conn.hmset(
            self.state_key_template.format_map(self.device.details),
            self.device.settings,
        )

    def load_state(self, state_source):
        # try to load state from fields of a glworb
        possible_state_source_fields = redis_conn.hgetall(state_source)
        # only use if correct scripts
        try:
            if (
                possible_state_source_fields["{}scripts".format(self.setting_prefix)]
                == self.device.details["scripts"]
            ):
                for k, v in possible_state_source_fields.items():
                    if k.startswith(self.setting_prefix):
                        # remove prefix before adding
                        self.device.settings[k[len(self.setting_prefix) :]] = v
                self.update_details()
        except KeyError:
            pass

    def set_device_setting(self, attribute, value, widget=None):
        self.device.settings[attribute] = value
        if widget:
            current_background = [1, 1, 1, 1]
            anim = Animation(background_color=[0, 1, 0, 1], duration=0.5) + Animation(
                background_color=current_background, duration=0.5
            )
            anim.start(widget)

    def check_call(self):
        if not self.view_call_input.text:
            self.view_call_input.text = self.default_view_call

    def preview(self, settings=None):
        if settings is None:
            for widget in self.settings_widgets:
                self.set_device_setting(widget.attribute, widget.text, widget)
            settings = self.device.settings
        # apply settings
        for setting, setting_value in settings.items():
            if setting_value:
                print(setting, setting_value, self.device.details)
                try:
                    self.app.device_classes[
                        self.device.details["discovery"]
                    ].set_setting(self.device.details, setting, setting_value)
                except Exception as ex:
                    print("setting: ", ex)
        # call may result in: [-108] File not found
        # if usb address has changed
        #
        # update devices again before calling
        self.app.update_devices()
        metadata = self.device.settings_prefixed(self.setting_prefix)
        slurped = self.app.device_classes[self.device.details["discovery"]].slurp(
            device=self.device.details, metadata=metadata
        )

        view_call = self.view_call_input.text
        for thing in slurped:
            call_dict = {
                "host": self.app.db_host,
                "port": self.app.db_port,
                "thing": thing,
                "thing_field": "binary_key",
            }
            view_call = view_call.format_map(call_dict)
            subprocess.Popen(view_call.split(" "))


class DevApp(App):
    def __init__(self, *args, **kwargs):
        # store kwargs to passthrough
        self.kwargs = kwargs
        if kwargs["db_host"] and kwargs["db_port"]:
            global binary_r
            global redis_conn
            db_settings = {"host": kwargs["db_host"], "port": kwargs["db_port"]}
            binary_r = redis.StrictRedis(**db_settings)
            redis_conn = redis.StrictRedis(**db_settings, decode_responses=True)

        self.db_port = redis_conn.connection_pool.connection_kwargs["port"]
        self.db_host = redis_conn.connection_pool.connection_kwargs["host"]
        self.env_key = "machinic:env:{}:{}".format(self.db_host, self.db_port)
        self.session_save_path = "~/.config/enn-ui/"
        self.session_save_filename = "session_{}_{}.xml".format(
            self.db_host, self.db_port
        )

        super(DevApp, self).__init__()

    def build(self):
        root = BoxLayout()
        self.device_container = BoxLayout()
        empty_notice_widget = Label(text="no devices. plug something in")
        self.device_container.empty_notice = empty_notice_widget
        root.add_widget(self.device_container)
        self.update_env_values()
        self.load_session()
        # classes for device discovery and interaction
        # .discover() is called for discovery
        self.device_classes = {}
        self.device_classes["gphoto2"] = sg.SlurpGphoto2(
            binary_r=binary_r, redis_conn=redis_conn
        )

        self.db_event_subscription = redis_conn.pubsub()
        self.db_event_subscription.psubscribe(
            **{"__keyspace@0__:*": self.handle_db_events}
        )
        # add thread to pubsub object to stop() on exit
        self.db_event_subscription.thread = self.db_event_subscription.run_in_thread(
            sleep_time=0.001
        )
        # monitor usb events to show local device connect / disconnect
        # there may be other sources that are accessible over the
        # db or network
        usb_event_thread = threading.Thread(target=self.usb_events)
        # end thread when window is closed
        usb_event_thread.daemon = True
        usb_event_thread.start()
        self.update_devices()
        self.placeholder()
        return root

    def placeholder(self):
        self.device_container.remove_widget(self.device_container.empty_notice)

        if not self.device_container.children:
            self.device_container.add_widget(self.device_container.empty_notice)

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
        self.device_container.remove_widget(self.device_container.empty_notice)

        for name, device_class in self.device_classes.items():
            discovered.extend(device_class.discover())

        # reset existing device connected status
        # before rediscovery / nondiscovery
        for child in self.device_container.children:
            child.device.connected = False
            child.update_details()

        for device in discovered:
            if not device["uid"] in [
                child.device.details["uid"] for child in self.device_container.children
            ]:
                device_widget = DeviceItem(app=self)
                device_widget.device.details = device
                device_widget.device.connected = True
                device_widget.update_details()
                self.device_container.add_widget(device_widget)
            else:
                for child in self.device_container.children:
                    if device["uid"] == child.device.details["uid"]:
                        child.device.connected = True
                        # update details since address may have changed
                        child.device.details.update(device)
                        child.update_details()

    def update_env_values(self):
        redis_conn.hgetall(self.env_key)

    def handle_db_events(self, message):
        msg = message["channel"].replace("__keyspace@0__:", "")
        if msg in (self.env_key):
            Clock.schedule_once(lambda dt: self.update_env_values(), .1)

    def load_session(self):
        expanded_path = os.path.expanduser(self.session_save_path)
        file = os.path.join(expanded_path, self.session_save_filename)
        try:
            xml = etree.parse(file)
            for session in xml.xpath("//session"):
                for device in session.xpath("//device"):
                    device_widget = DeviceItem(app=self)
                    device_widget.device.details = device.attrib
                    for settings in session.xpath("//settings"):
                        device_widget.device.settings = settings.attrib
                    device_widget.update_details()
                    self.device_container.add_widget(device_widget)
        except OSError as ex:
            pass

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
        for device in [
            child.device
            for child in self.device_container.children
            if hasattr(child, "device")
        ]:
            dev = etree.Element("device")
            for k, v in device.details.items():
                try:
                    dev.set(k, v)
                except TypeError:
                    # scripts None
                    pass

            settings = etree.Element("settings")
            for k, v in device.settings.items():
                settings.set(k, v)
            dev.append(settings)
            session.append(dev)
        machine_root = etree.ElementTree(machine)

        if os.path.isfile(os.path.join(expanded_path, self.session_save_filename)):
            os.remove(os.path.join(expanded_path, self.session_save_filename))

        machine_root.write(
            os.path.join(expanded_path, self.session_save_filename), pretty_print=True
        )

    def on_stop(self):
        # stop pubsub thread if window closed with '[x]'
        self.db_event_subscription.thread.stop()

    def app_exit(self):
        self.db_event_subscription.thread.stop()
        App.get_running_app().stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-key", help="db hash key")
    parser.add_argument("--db-key-field", help="db hash field")

    parser.add_argument("--db-host", help="db host ip, requires use of --db-port")
    parser.add_argument(
        "--db-port", type=int, help="db port, requires use of --db-host"
    )
    args = parser.parse_args()

    if bool(args.db_host) != bool(args.db_port):
        parser.error("--db-host and --db-port values are both required")

    app = DevApp(**vars(args))
    atexit.register(app.save_session)
    app.run()
