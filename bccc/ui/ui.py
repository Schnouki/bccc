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
import os
import queue
import subprocess
import threading

import urwid

from bccc.ui import ChannelsList, ThreadsBox
from .util import SmartStatusBar

# {{{ UI class
class UI:
    """The Urwid UI"""

    # {{{ Constructor
    def __init__(self, conf, client):
        self.conf = conf
        self.client = client

        # {{{ Palette
        palette = []
        for key, val in conf.items("ui"):
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
        self.channels.load_channels()
        self.loop.run()

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
        self._cb_queue.put((self.status.set_text, [txt], {}))
        os.write(self._cb_fd, b"x")
    # }}}
    # {{{ Desktop interaction
    def open_urls(self, *urls):
        def _open_urls():
            for url in urls:
                subprocess.call([self.conf.get("url", "opener"), url])
        thr = threading.Thread(target=_open_urls)
        thr.daemon = True
        thr.start()
    # }}}
# }}}
# Local Variables:
# mode: python3
# End:
