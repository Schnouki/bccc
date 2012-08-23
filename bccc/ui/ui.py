# Copyright 2012 Thomas Jost
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software stributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import functools
import logging
import os
import os.path
import queue
import sys
import threading

import urwid

import bccc.client
from bccc.ui import ChannelsList, ThreadsBox
from .util import SmartStatusBar

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# {{{ UI class
class UI:
    """The Urwid UI"""

    # {{{ Constructor
    def __init__(self, conf, theme):
        self.conf = conf

        # {{{ Early logging
        class EarlyFormatter(logging.Formatter):
            def format(self, record):
                if record.levelno == logging.INFO:
                    return record.message
                else:
                    return "[{record.levelname}] {record.message}".format(record=record)

        self._early_log = logging.StreamHandler(stream=sys.stderr)
        self._early_log.setLevel(logging.INFO)
        self._early_log.setFormatter(EarlyFormatter())

        logging.getLogger("").addHandler(self._early_log)
        # }}}
        # {{{ Client
        # Get credentials
        if not conf.has_option("buddycloud", "jid") or not conf.has_option("buddycloud", "password"):
            print("JID and/or password is missing in configuration file", file=sys.stderr)
            sys.exit(1)

        jid, password = conf.get("buddycloud", "jid"), conf.get("buddycloud", "password")
        self.client = bccc.client.Client(jid, password)

        address = ()
        if conf.has_option("buddycloud", "host"):
            host = conf.get("buddycloud", "host")
            port = 5222
            if conf.has_option("buddycloud", "port"):
                port = conf.getint("buddycloud", "port")
            address = (host, port)
        elif conf.has_option("buddycloud", "port"):
            print("Please specify a hostname if you want to use a custom XMPP client port.", file=sys.stderr)

        if conf.has_option("buddycloud", "use_ipv6"):
            self.client.use_ipv6 = conf.get("buddycloud", "use_ipv6")

        use_tls = True
        if conf.has_option("buddycloud", "use_tls"):
            use_tls = conf.getboolean("buddycloud", "use_tls")

        print("Logging in as {jid}...".format(jid=jid), file=sys.stderr)
        if not self.client.connect(address=address, use_tls=use_tls):
            print("Unable to connect to server!", file=sys.stderr)
            sys.exit(1)

        # Run client.process() in a daemonized thread to avoid blocking when exiting
        client_thread = threading.Thread(target=lambda: self.client.process(block=True))
        client_thread.daemon = True
        client_thread.start()
        # }}}
        # {{{ Palette
        palette = []
        for key, val in theme.items():
            attr = [a.strip() for a in val.split(";")]
            # Make sure there are enough entries
            if len(attr) in (1, 4):
                attr.append("")
            # For the first 3 values, replace "" with "default". For 4 and 5,
            # replace "" with None.
            for i in (0, 1, 2):
                if len(attr) > i and len(attr[i]) == 0:
                    attr[i] = "default"
            for i in (3, 4):
                if len(attr) > i and len(attr[i]) == 0:
                    attr[i] = None

            palette.append([key])
            palette[-1].extend(attr)
        # }}}
        # {{{ Widgets
        # Sidebar
        self.channels = ChannelsList(self)
        channels_am = urwid.AttrMap(self.channels, "sidebar")

        # Info bar
        self.infobar_left  = urwid.Text("")
        self.infobar_right = urwid.Text("", align="right")

        infobar_left_am  = urwid.AttrMap(self.infobar_left, "info bar left")
        infobar_right_am = urwid.AttrMap(self.infobar_right, "info bar right")
        infobar = urwid.Columns([infobar_left_am, ("flow", infobar_right_am)], dividechars=1)
        infobar_am = urwid.AttrMap(infobar, "info bar")

        # Main pane
        self.threads_list = ThreadsBox(self)
        main_pane = urwid.Frame(self.threads_list, header=infobar_am)

        # Columns
        cols = [
            ("weight", 0.2, channels_am),
            ("weight", 0.8, main_pane),
        ]
        columns = urwid.Columns(cols, min_width=15)

        # Status bar
        self.status = SmartStatusBar()

        # Main frame
        frame = urwid.Frame(columns, footer=self.status)
        self.status.set_frame(frame)
        # }}}

        # Main loop
        self.loop = urwid.MainLoop(frame, palette,
                                   input_filter    = self.input_filter,
                                   unhandled_input = self.unhandled_input)

        # {{{ Callbacks
        # Thread-safe callbacks and requests
        self._refresh_fd = self.loop.watch_pipe(self._draw_screen)
        self._cb_queue = queue.Queue()
        self._cb_fd = self.loop.watch_pipe(self._handle_callback)
        # }}}
    # }}}
    # {{{ Urwid run-time
    def run(self):
        # Make sure the client is ready
        self.client.ready()

        # Once ready, disable early logging
        logging.getLogger("").removeHandler(self._early_log)

        # Load subscribed channels and start the UI
        print("Loading subscribed channels", file=sys.stderr)
        self.channels.load_channels()
        print("Starting the UI", file=sys.stderr)
        self.loop.run()

        # Clear XTerm alternate buffer before exiting
        print("\033[?47h\033[2J\033[?47l", end="")

        # About to exit: do some cleanup
        self.client.disconnect()
        print("Bye bye!", file=sys.stderr)

    def input_filter(self, keys, raw):
        return keys

    def unhandled_input(self, input):
        if input == "q":
            raise urwid.ExitMainLoop()
        elif input == "=":
            self.channels.reset()
            self.loop.draw_screen()
        elif input == "g":
            self.channels.goto()
    # }}}
    # {{{ Thread-safe callbacks and requests
    def refresh(self):
        os.write(self._refresh_fd, b"x")

    def _draw_screen(self, data=None):
        self.loop.draw_screen()
        return True

    def safe_callback(self, func):
        @functools.wraps(func)
        def callback_wrapper(*args, **kwargs):
            self._cb_queue.put((func, args, kwargs))
            os.write(self._cb_fd, b"x")
        return callback_wrapper

    def _handle_callback(self, data=None):
        # There may be several callbacks pending (nice event loop optimization!). So we need to loop.
        try:
            while True:
                (func, args, kwargs) = self._cb_queue.get(block=False)
                func(*args, **kwargs)
                self._cb_queue.task_done()
        except queue.Empty:
            pass

    def safe_status_set_text(self, txt):
        """Thread-safe, queued version of ui.status.set_text()

        Mostly for use in Urwid interals, where changing the status text could
        change a widget's size in the middle of a rendering process."""
        self.safe_callback(self.status.set_text)(txt)
    # }}}
    # {{{ Desktop interaction
    def open_urls(self, *urls):
        def call(exe, *args):
            # Double-fork to detach from parent process
            if os.fork() == 0:
                # First child: de-couple from environment, re-fork and exit
                os.chdir("/")
                os.setsid()
                os.umask(0)

                if os.fork() != 0:
                    os._exit(0)

                # Second child: close file descriptors so the child does not
                # pollute our beloved stdout/stderr, and run the command
                os.closerange(1, 1024)

                # And now run the command
                cmd = [os.path.basename(exe)] + list(args)
                os.execvp(exe, cmd)
            else:
                os.wait()

        opener = self.conf.get("url", "opener")
        for url in urls:
            call(opener, url)

    def notify(self):
        # Console beep -- good terminal emulators map this to the X11 "urgency" hint
        if (not self.conf.has_option("ui", "console_beep")) or self.conf.getboolean("ui", "console_beep"):
            print("\a", end="")
    # }}}
# }}}
# Local Variables:
# mode: python3
# End:
