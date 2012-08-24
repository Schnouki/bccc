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

import datetime
import operator as op

import urwid

from bccc.client import ChannelError
from bccc.ui import Cache

# {{{ Channel box
class ChannelBox(urwid.widget.BoxWidget):
    def __init__(self, ui, channel):
        self.ui = ui
        self.channel = channel
        self.cache = Cache(ui.loop, ui.client.boundjid.bare, channel.jid)
        self.active = False
        self.unread_ids = set()

        # Init sub-widgets
        w = urwid.Text("", wrap="clip")
        w = urwid.AttrMap(w, "channel user", "focused channel user")
        self.widget_user = w

        w = urwid.Text("", wrap="clip")
        w = urwid.AttrMap(w, "channel domain", "focused channel domain")
        self.widget_domain = w

        w = urwid.Text("", align="right", wrap="clip")
        w = urwid.AttrMap(w, "channel notif", "focused channel notif")
        self.widget_notif = w

        w = urwid.Text("")
        w = urwid.AttrMap(w, "channel status", "focused channel status")
        self.widget_status = w

        # Set title to JID until we now more
        self.set_title(channel.jid)

        # Channel configuration
        self.chan_title = ""
        self.chan_description = ""
        self.chan_creation = None
        self.chan_type = ""

        # Load data from cache
        self.set_config(self.cache.config, False)
        status = self.cache.status
        if status is not None:
            self.widget_status.original_widget.set_text(status)
        self.last_update = self.cache.last_update

        # Channel callbacks
        _callbacks = {
            "cb_post":    ui.safe_callback(self.pubsub_posts_callback),
            "cb_retract": ui.safe_callback(self.pubsub_retract_callback),
            "cb_status":  ui.safe_callback(self.pubsub_status_callback),
            "cb_config":  ui.safe_callback(self.pubsub_config_clalback),
        }
        channel.set_callbacks(**_callbacks)

        # Request missing informations
        channel.pubsub_get_config()

        if self.last_update == Cache.never:
            channel.pubsub_get_status()
            channel.pubsub_get_posts(max=20)

    # {{{ PubSub Callbacks
    def pubsub_posts_callback(self, atoms):
        new_atoms = []
        for atom in atoms:
            if self.cache.add_item(atom):
                new_atoms.append(atom)

        # Find most recent atom
        recent_changed = self.last_update != self.cache.last_update
        self.last_update = self.cache.last_update

        # Tell the ChannelsList to sort channels again
        if recent_changed:
            self.ui.channels.sort_channels()

        if self.active:
            # Notify the content pane
            # TODO: more?
            self.ui.threads_list.add_new_items(new_atoms)
        else:
            # Update unread counter
            for a in new_atoms:
                self.unread_ids.add(a.id)
            nb_unread = len(self.unread_ids)
            if nb_unread > 0:
                self.widget_notif.original_widget.set_text(" [{}]".format(nb_unread))
                self._invalidate()

        self.ui.notify()

    def pubsub_retract_callback(self, item_ids):
        for id_ in item_ids:
            self.unread_ids.discard(id_)
            self.cache.del_item(id_)
        if self.active:
            self.ui.threads_list.remove_items(item_ids)
        self.ui.channels.sort_channels()

    def pubsub_status_callback(self, atom):
        txt = atom.content
        self.widget_status.original_widget.set_text(txt)
        self.cache.status = txt
        self._invalidate()

    def pubsub_config_clalback(self, conf):
        self.set_config(conf)
    # }}}
    # {{{ Channel management
    def set_active(self, active):
        self.active = active
        if active:
            self.widget_user.set_attr_map({None: "active channel user"})
            self.widget_user.set_focus_map({None: "focused active channel user"})
            self.widget_domain.set_attr_map({None: "active channel domain"})
            self.widget_domain.set_focus_map({None: "focused active channel domain"})
            self.widget_notif.set_attr_map({None: "active channel notif"})
            self.widget_notif.set_focus_map({None: "focused active channel notif"})
            self.widget_status.set_attr_map({None: "active channel status"})
            self.widget_status.set_focus_map({None: "focused active channel status"})

            self.widget_notif.original_widget.set_text("")
            self.unread_ids.clear()

            self.display_config()
        else:
            self.widget_user.set_attr_map({None: "channel user"})
            self.widget_user.set_focus_map({None: "focused channel user"})
            self.widget_domain.set_attr_map({None: "channel domain"})
            self.widget_domain.set_focus_map({None: "focused channel domain"})
            self.widget_notif.set_attr_map({None: "channel notif"})
            self.widget_notif.set_focus_map({None: "focused channel notif"})
            self.widget_status.set_attr_map({None: "channel status"})
            self.widget_status.set_focus_map({None: "focused channel status"})

    def display_config(self):
        if self.active:
            self.ui.infobar_left.set_text("{} - {}".format(self.chan_title, self.chan_description))
            self.ui.infobar_right.set_text(self.channel.jid)

    def set_status(self, status):
        self.widget_status.original_widget.set_text(status)
        self._invalidate()

    def set_title(self, title):
        self.chan_title = title

        # What should we display in the sidebar?
        user, domain = title, ""
        jid = self.channel.jid
        if len(title) == 0:
            title = jid
        if jid.lower() == title.lower():
            user, domain = title.split("@", 1)

            # Shorten my.long.domain.name into "mldn"
            domain = "@" + "".join([w[0] for w in domain.split(".")])

        self.widget_user.original_widget.set_text(user)
        self.widget_domain.original_widget.set_text(domain)

    def set_config(self, config, cache=True):
        if "title" in config:
            self.set_title(config["title"].strip())
        if "description" in config:
            self.chan_description = config["description"].strip()
        if "creation" in config:
            self.chan_creation = config["creation"]
        if "type" in config:
            self.chan_type = config["type"]

        if cache:
            self.cache.config = {
                "title": self.chan_title,
                "description": self.chan_description,
                "creation": self.chan_creation,
                "type": self.chan_type,
            }

        self.display_config()
        self._invalidate()
    # }}}
    # {{{ Widget management
    def keypress(self, size, key):
        return key

    def rows(self, size, focus=False):
        return 1 + self.widget_status.rows(size, focus)

    def render(self, size, focus=False):
        maxcol = size[0]

        # First line: user, shortened domain, notif
        canv1, comb1 = None, None
        user_col, _ = self.widget_user.pack(focus=focus)
        if len(self.unread_ids) == 0:
            # No notification: just user + domain
            domain_col  = maxcol - user_col
            if domain_col > 0:
                canv_user = self.widget_user.render((user_col,), focus)
                canv_domain = self.widget_domain.render((domain_col,), focus)
                comb1 = [(canv_user,   None, True, user_col),
                         (canv_domain, None, True, domain_col)]
            else:
                canv1 = self.widget_user.render(size, focus)
        else:
            # There are notifications: now it's tricker
            notif_col, _ = self.widget_notif.pack(focus=focus)
            domain_col   = maxcol - user_col - notif_col
            if domain_col > 0:
                # Render everything!
                canv_user = self.widget_user.render((user_col,), focus)
                canv_domain = self.widget_domain.render((domain_col,), focus)
                canv_notif = self.widget_notif.render((notif_col,), focus)
                comb1 = [(canv_user,   None, True, user_col),
                         (canv_domain, None, True, domain_col),
                         (canv_notif,  None, True, notif_col)]
            else:
                # Only user and notif.
                user_col  = min(user_col, maxcol - notif_col)
                if user_col > 0:
                    # User + notif
                    canv_user = self.widget_user.render((user_col,), focus)
                    canv_notif = self.widget_notif.render((notif_col,), focus)
                    comb1 = [(canv_user,  None, True, user_col),
                             (canv_notif, None, True, notif_col)]
                else:
                    # Notif only
                    canv1 = self.widget_notif.render(size, focus)

        if comb1 is not None:
            canv1 = urwid.CanvasJoin(comb1)

        # Second (status)
        canv_status = self.widget_status.render(size, focus)

        # Combine lines
        combinelist = [(c, None, True) for c in (canv1, canv_status)]
        return urwid.CanvasCombine(combinelist)
    # }}}
# }}}
# {{{ Channels list
class ChannelsList(urwid.ListBox):
    """A list of channels"""

    def __init__(self, ui):
        self.ui = ui

        # Init ListBox with a SimpleListWalker
        self._channels = urwid.SimpleListWalker([])
        urwid.ListBox.__init__(self, self._channels)

        # No active channel for now
        self.active_channel = None

    def keypress(self, size, key):
        if key == "enter":
            focus_w, _ = self.get_focus()
            self.make_active(focus_w)
        else:
            return urwid.ListBox.keypress(self, size, key)

    def load_channels(self):
        # Request user channel
        user_chan = self.ui.client.get_channel()

        # Request user subscriptions
        chans = user_chan.get_subscriptions()

        # First empty the list
        del self._channels[:]

        # Then add each channel to it
        for chan in chans:
            w = ChannelBox(self.ui, chan)
            if chan.jid == self.ui.client.boundjid.bare:
                self._channels.insert(0, w)
                self.make_active(w)
            else:
                self._channels.append(w)

        # Find the oldest mtime
        mtime = min(self._channels, key=op.attrgetter("cache.mtime")).cache.mtime

        # ...and MAM a little earlier :)
        if mtime > Cache.never:
            mtime -= datetime.timedelta(hours=1)
            self.ui.client.mam(start=mtime)

        # A nice divider :)
        self._channels.insert(1, urwid.Divider("─"))

        # Because of the cache, we already need to sort now.
        self.sort_channels()

        self.ui.refresh()

    def sort_channels(self):
        focus_w, _ = self.get_focus()
        sortable_chans = self._channels[2:]
        sortable_chans.sort(key=op.attrgetter("last_update"), reverse=True)
        self._channels[2:] = sortable_chans
        focus_pos = self._channels.index(focus_w)
        self.set_focus(focus_pos)
        self._invalidate()

    def reset(self):
        """Reset active channel. This is *violent*."""
        chan_box = self.active_channel
        idx = self._channels.index(chan_box)

        try:
            new_chan = self.ui.client.get_channel(chan_box.channel.jid, force_new=True)
        except ChannelError:
            return # TODO: display warning
        chan_box.cache.delete()
        new_chan_box = ChannelBox(self.ui, new_chan)
        self._channels[idx] = new_chan_box
        self.make_active(new_chan_box)

    def make_active(self, chan):
        if self.active_channel is chan:
            return
        self.ui.status.set_text("Displaying channel {}...".format(chan.channel.jid))
        if self.active_channel is not None:
            self.active_channel.set_active(False)
        self.active_channel = chan
        chan.set_active(True)
        self.ui.threads_list.set_active_channel(chan.channel, chan.cache)

    def goto(self, jid=None):
        def _goto_channel(jid):
            jid = jid.strip()
            chan_idx = None

            # Is the jid in the channels list?
            for idx, chan in enumerate(self._channels):
                if type(chan) is ChannelBox and chan.channel.jid == jid:
                    chan_idx = idx
                    break

            # If it's not, add it
            if chan_idx is None:
                try:
                    channel = self.ui.client.get_channel(jid)
                except ChannelError:
                    return # TODO: display warning
                chan = ChannelBox(self.ui, channel)
                self._channels.append(chan)
                chan_idx = len(self._channels) - 1

            # Give focus and make channel active
            chan = self._channels[chan_idx]
            self.set_focus(chan_idx)
            self.make_active(chan)

        if jid is None:
            self.ui.status.ask("Go to channel: ", _goto_channel)
        else:
            _goto_channel(jid)
# }}}
# Local Variables:
# mode: python3
# End:
