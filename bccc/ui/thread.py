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

import bisect

import urwid

from bccc.ui import ItemWidget, PostWidget, ReplyWidget, \
                    NewPostWidget, NewReplyWidget
from .util import extract_urls

# {{{ ThreadList helper
class ThreadList(list):
    @property
    def date(self):
        return self[-1].item.published

    @property
    def id(self):
        return self[0].id

    def __lt__(self, other):
        return self.date > other.date # ">" because we want to sort threads by newer first

    def __eq__(self, other):
        return type(other) is ThreadList and self.id == other.id
# }}}
# {{{ ThreadsWalker
class ThreadsWalker(urwid.ListWalker):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self.channel = None
        self.more_posts_requested = False
        self.oldest_item = None
        self.items_iterator = None
        self.focus_item = (None, None)

        # Indicator that status bar should not be updated while rendering
        self.block_status_update = False

        # Extra widget: new post or new reply
        self.extra_widget = None
        self.focus_before_extra_widget = None

        # A list of ThreadList, newest thread first
        self.threads = []
        self.flat_threads = None

    # {{{ Internal helpers
    def _modified(self, flatten=True):
        if flatten:
            self._flatten()
            focus_w = self.focus_item[0]
            if self.focus_item[0] is None or self.focus_item[1] is None:
                if len(self.flat_threads) > 0:
                    self.focus_item = (self.flat_threads[0], 0)
                else:
                    self.focus_item = (None, None)
            elif self.focus_item[0] is not self.flat_threads[self.focus_item[1]]:
                # Mismatch - try to keep the widget focused
                w, pos = self.focus_item
                try:
                    pos = self.flat_threads.index(w)
                except ValueError:
                    # Widget not found - keep position
                    w = self.flat_threads[pos]
                self.focus_item = (w, pos)
        super()._modified()

    def _flatten(self):
        self.flat_threads = []

        # Handle new post/reply widget
        reply_thr_id = None
        if type(self.extra_widget) is NewPostWidget:
            self.flat_threads = [self.extra_widget]
        elif type(self.extra_widget) is NewReplyWidget:
            reply_thr_id = self.extra_widget.thread_id

        for thr in self.threads:
            self.flat_threads.extend(thr)
            if thr.id == reply_thr_id:
                self.flat_threads.append(self.extra_widget)
            self.flat_threads.append(urwid.Divider(" "))
    # }}}
    # {{{ ListWalker interface
    def get_focus(self):
        return self.focus_item

    def set_focus(self, position):
        item = self.flat_threads[position]
        self.focus_item = (item, position)

        if not self.block_status_update:
            # Which thread number is that?
            for (pos, thr) in enumerate(self.threads):
                if item in thr:
                    thr_nb = pos+1
                    self.ui.status.set_text("{}: thread {}/{}".format(self.channel.jid, thr_nb, len(self.threads)))
                    break

        self._modified(False)

    def get_prev(self, position):
        if position == 0:
            return None, None
        else:
            return (self.flat_threads[position-1], position-1)

    def get_next(self, position):
        # Load new items if we're close to the end of the channel
        if position >= len(self.flat_threads) - 40:
            self._load_more_posts()
        if position < len(self.flat_threads)-1:
            return (self.flat_threads[position+1], position+1)
        else:
            return None, None
    # }}}
    # {{{ Channel management
    def set_channel(self, channel):
        del self.threads[:]
        self.extra_widget = None
        self.channel = channel
        self.focus_item = (None, None)

        self.more_posts_requested = False
        self.oldest_item = None
        for atom in self.channel:
            self.add(atom)
        if len(self.threads) < 1:
            self._load_more_posts()

        self._modified()

    def _load_more_posts(self):
        if not self.more_posts_requested:
            after_id = None
            if self.oldest_item is not None:
                after_id = self.oldest_item.id
            self.channel.pubsub_get_posts(max=50, after=after_id)
            self.more_posts_requested = True

    def get_focused_post_urls(self):
        w = self.focus_item[0]
        if isinstance(w, PostWidget):
            txt = w.item.content
            return list(extract_urls(txt))

    def goto_focused_post_channel(self):
        w = self.focus_item[0]
        if isinstance(w, PostWidget):
            jid = w.item.author
            self.ui.channels.goto(jid)
    # }}}
    # {{{ Threads management
    def add(self, item):
        self.more_posts_requested = False
        if self.oldest_item is None or item.published < self.oldest_item.published:
            self.oldest_item = item

        # Find thread ID
        thr_id = item.id
        item_is_post = True
        if item.object_type == "comment":
            item_is_post = False
            thr_id = item.in_reply_to
        pos_thr = self.find_thread_by_id(thr_id)

        if pos_thr is None:
            # New thread!
            thr = ThreadList()
            if item_is_post:
                thr.append(PostWidget(item))
            else:
                # We need a placeholder!
                thr.insert(0, ItemWidget(thr_id, " ", " ", "[post not loaded yet]"))
                thr.append(ReplyWidget(item))

            bisect.insort_left(self.threads, thr)

        else:
            # New post/reply in existing thread!
            pos, thr = pos_thr
            if item_is_post:
                # Replace placeholder with this one
                thr[0] = PostWidget(item)
            else:
                # Add reply at the right position. A simple bisect.insort_left()
                # should be enough, but since a reply may already have been
                # loaded previously by _load_thread(), we need to be a little
                # more careful.
                w = ReplyWidget(item)
                reply_pos = bisect.bisect_left(thr, w, lo=1)
                if reply_pos >= len(thr):
                    thr.append(w)
                elif thr[reply_pos].id != item.id:
                    thr.insert(reply_pos, w)
                # TODO: what about existing replies that have been updated?

            # This may have changed the thread date, so we need to recompute its position in the list
            new_pos = bisect.bisect_left(self.threads, thr)
            if new_pos < pos:
                del self.threads[pos]
                self.threads.insert(new_pos, thr)
            elif new_pos > pos:
                self.threads.insert(new_pos, thr)
                del self.threads[pos]

    def find_thread_by_id(self, thr_id):
        for pos, thr in enumerate(self.threads):
            if thr.id == thr_id:
                return (pos, thr)
    # }}}
    # {{{ New post/reply management
    def new_post(self):
        """Create a NewPostWidget and put it on top of the posts list."""
        self.focus_before_extra_widget = self.focus_item
        self.extra_widget = NewPostWidget(self.ui, self.channel)
        self._modified()

    def new_reply(self):
        """Create a NewReplyWidget and put it at the end of the current thread. Return its position."""
        focus_w = self.focus_item[0]

        thr_id = None
        if hasattr(focus_w, "in_reply_to"):
            thr_id = focus_w.in_reply_to
        elif hasattr(focus_w, "id"):
            thr_id = focus_w.id
        else:
            # The focused item is probably not a post or a thread. Maybe a
            # divider, maybe something else?...
            return

        self.focus_before_extra_widget = self.focus_item
        self.extra_widget = NewReplyWidget(self.ui, self.channel, thr_id)
        self._modified()
        return self.flat_threads.index(self.extra_widget)

    def remove_extra_widget(self):
        if self.extra_widget is not None:
            self.extra_widget = None
            self.ui.status.set_text("")
            self.focus_item = self.focus_before_extra_widget
            self._modified()
    # }}}
# }}}
# {{{ ThreadsBox
class ThreadsBox(urwid.ListBox):
    def __init__(self, ui):
        self.ui = ui
        self.content = ThreadsWalker(ui)
        self._pref_col = 0
        super().__init__(self.content)

    # Lame workaround for an Urwid bug: rendering a ListBox can trigger 2 calls
    # to ListWalker.set_focus(). Which, here, will change the status bar,
    # possibly changing the number of lines required to render it, causing
    # render to fail with an assertion error.
    def render(self, *args, **kwds):
        self.content.block_status_update = True
        ret = super().render(*args, **kwds)
        self.content.block_status_update = False
        return ret

    # Stupid and ugly workaround for an Urwid bug: self.pref_col can be "left"
    # or "right", but parts of the code assume it's an integer and compare it
    # with another integer.
    @property
    def pref_col(self):
        return self._pref_col
    @pref_col.setter
    def pref_col(self, value):
        if value == "left": value=0
        elif value == "right": value=None
        self._pref_col = value

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == "d":
            self.update_description()
        elif key == "G":
            self.content.goto_focused_post_channel()
        elif key == "n":
            self.new_post(size)
        elif key == "o":
            urls = self.content.get_focused_post_urls()
            self.ui.open_urls(*urls)
        elif key == "r":
            self.new_reply(size)
        elif key == "s":
            self.update_status()
        elif key == "t":
            self.update_title()
        else:
            return key

    def add_new_items(self, items):
        for item in items:
            self.content.add(item)
        self.content._modified()

    def cancel_new_item(self):
        self.content.remove_extra_widget()

    def new_post(self, size):
        # Create a new post, on top of the list
        self.content.new_post()
        self.change_focus(size, 0, coming_from="below")

    def new_reply(self, size):
        # Create a new reply, trying not to move the rest of the screen.
        pos = self.content.new_reply()
        if pos is not None:
            self.set_focus(pos, coming_from="above")

    def set_active_channel(self, channel):
        self.content.set_channel(channel)

    def update_description(self):
        def _set_desc(text):
            text = text.strip()
            if len(text) > 0:
                self.content.channel.update_config(description=text)
        self.ui.status.ask("New channel description: ", _set_desc)

    def update_status(self):
        def _set_status(text):
            text = text.strip()
            if len(text) > 0:
                self.content.channel.set_status(text)
        self.ui.status.ask("New status message: ", _set_status)

    def update_title(self):
        def _set_title(text):
            text = text.strip()
            if len(text) > 0:
                self.content.channel.update_config(title=text)
        self.ui.status.ask("New channel title: ", _set_title)
# }}}
# Local Variables:
# mode: python3
# End: