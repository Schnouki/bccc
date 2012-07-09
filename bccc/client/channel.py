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
from xml.etree import cElementTree as ET
import logging
import threading

import dateutil.parser

from bccc.client import Atom, ATOM_NS, ATOM_THR_NS, UpdatableAtomsList

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# {{{ Exceptions
class ChannelError(Exception):
    """A generic error in a buddycloud channel"""
    pass
class InvalidChannelName(ChannelError):
    """Invalid channel name, such as user@ or @topics.buddycloud.org"""
    def __init__(self, jid):
        msg = "Invalid channel name: {}".format(jid)
        log.warning(msg)
        super().__init__(msg)
# }}}
# {{{ Channels
class Channel:
    """A buddycloud channel, tied to a client"""

    # {{{ Channel init
    CONFIG_MAP = (
        ("title",       "pubsub#title"),
        ("description", "pubsub#description"),
        ("creation",    "pubsub#creation_date"),
        ("type",        "buddycloud#channel_type")
    )

    def __init__(self, client, jid):
        log.debug("Initializing channel %s", jid)

        # Avoid invalid channel names
        user, domain = jid.split("@", 1)
        if len(user) == 0 or len(domain) == 0:
            raise InvalidChannelName(jid)

        self.client = client
        self.jid = jid

        # All the channels items, newest first (as returned by the server)
        self.atoms = UpdatableAtomsList()
        self.atoms_lock = threading.RLock()
        self.load_event = threading.Event()
        self.loading = False
        self.oldest_id = None

        # Callbacks
        self.callback_config  = None
        self.callback_post    = None
        self.callback_retract = None
        self.callback_status  = None

    def __iter__(self):
        return iter(self.atoms)

    def __repr__(self):
        return "<bccc.client.Channel {}>".format(self.jid)

    def set_callbacks(self, cb_config=None, cb_post=None, cb_retract=None, cb_status=None):
        if cb_config is not None:
            self.callback_config = cb_config
        if cb_post is not None:
            self.callback_post = cb_post
        if cb_retract is not None:
            self.callback_retract = cb_retract
        if cb_status is not None:
            self.callback_status = cb_status
    # }}}
    # {{{ Subscriptions/affiliations
    def get_subscriptions(self):
        channels = []
        subnode = "/user/" + self.jid + "/subscriptions"
        items = self.client.ps.get_items(self.client.channels_jid, subnode, block=True)
        for item in items["pubsub"]["items"]:
            try:
                chan = self.client.get_channel(item["id"])
                channels.append(chan)
            except ChannelError:
                pass
        return channels
    # }}}
    # {{{ PubSub event handlers
    def handle_post_event(self, entries):
        # Incoming entries: add them and trigger the callback
        if len(entries) == 0:
            return
        atoms = []
        for elt in entries:
            a = self.atoms.add(elt)
            if a is not None:
                atoms.append(a)
        if len(atoms) > 0 and self.callback_post is not None:
            self.callback_post(atoms)

    def handle_retract_event(self, entries):
        if len(entries) == 0:
            return
        # Remove retracted items from self.atoms
        with self.atoms_lock:
            for id_ in entries:
                self.atoms.remove(id_)
        if self.callback_retract is not None:
            self.callback_retract(entries)

    def handle_status_event(self, entries):
        if len(entries) == 0:
            return
        elt = entries[0]
        if elt is not None:
            a = Atom(elt)
            if self.callback_status is not None:
                self.callback_status(a)

    def handle_config_event(self, config_events):
        for conf in config_events:
            # Convert conf to a dict
            val = conf["form"]["values"]
            config = {}
            for (dk, ik) in self.CONFIG_MAP:
                if ik in val:
                    config[dk] = val[ik].strip()
            if "creation" in config:
                config["creation"] = dateutil.parser.parse(config["creation"])

            if self.callback_config is not None:
                self.callback_config(config)
    # }}}
    # {{{ PubSub requests
    def pubsub_get_items(self, node, callback, max=None, before=None, after=None):
        """
        Request the contents of a node's items.

        This is based on sleekxmpp.plugins.xep_0060.pubsub.xep_0060.get_items(),
        but uses XEP-0059 instead of the "max_items" attribute (cf.
        XEP-0060:6.5.7).
        """
        iq = self.client.ps.xmpp.Iq(sto=self.client.channels_jid, stype="get")
        iq["pubsub"]["items"]["node"] = node
        if max is not None:
            iq["pubsub"]["rsm"]["max"] = str(max)
        if before is not None:
            iq["pubsub"]["rsm"]["before"] = before
        if after is not None:
            iq["pubsub"]["rsm"]["after"] = after

        iq.send(callback=callback)

    def pubsub_get_post(self, item_id):
        def _add_post(items):
            elt = items["pubsub"]["items"]["item"].get_payload()
            with self.atoms_lock:
                a = self.atoms.add(elt)
            if a is not None and self.callback_post is not None:
                self.callback_post([a])

        node = "/user/{}/posts".format(self.jid)
        self.client.ps.get_item(self.client.channels_jid, node, item_id, block=False, callback=_add_post)

    def pubsub_get_posts(self, max=None, before=None, after=None):
        def _items_to_atom(items):
            atoms = []
            with self.atoms_lock:
                for item in items["pubsub"]["items"]:
                    elt = item.get_payload()
                    a = self.atoms.add(elt)
                    if a is not None:
                        atoms.append(a)
            if len(atoms) > 0 and self.callback_post is not None:
                self.callback_post(atoms)

        node = "/user/{}/posts".format(self.jid)
        return self.pubsub_get_items(node, _items_to_atom, max, before, after)

    def pubsub_get_status(self):
        def _status_cb(items):
            entries = [item.get_payload() for item in items["pubsub"]["items"]]
            while None in entries:
                entries.remove(None)
            if len(entries) > 0:
                self.handle_status_event(entries)

        node = "/user/{}/status".format(self.jid)
        self.pubsub_get_items(node, callback=_status_cb, max=1)

    def pubsub_get_config(self):
        def _config_cb(iq):
            conf = iq["pubsub_owner"]["configure"]
            self.handle_config_event([conf])

        node = "/user/{}/posts".format(self.jid)
        self.client.ps.get_node_config(self.client.channels_jid, node, callback=_config_cb)
    # }}}
    # {{{ Thread loading
    def get_partial_thread(self, first_id, last_id, callback):
        # Hard to read. Sorry.
        thread_atoms = []

        def _add_posts(atoms):
            thread_atoms.extend(atoms)
            thread_atoms.sort()

            # Did we find the last ID?
            found = False
            for a in atoms:
                if a.id == last_id:
                    found = True
                    break
            if found or len(atoms) == 0:
                # End here
                callback(thread_atoms)
            else:
                # Last ID not found yet: requests more posts
                self.pubsub_get_posts(_add_posts, max=20, before=thread_atoms[0].id)

        def _add_post(a):
            if a is not None:
                thread_atoms.append(a)

            # Request next items
            self.pubsub_get_posts(_add_posts, max=20, before=first_id)

        # Request first ID
        self.pubsub_get_post(_add_post, first_id, cb_if_empty=True)
    # }}}
    # {{{ Items publishing
    def _make_atom(self, text, author_name=None, in_reply_to=None, update_time=None):
        # Build something that looks like an Atom and return it
        entry = ET.Element("entry", xmlns=ATOM_NS)

        if author_name is None:
            author_name = self.client.boundjid.bare
        if update_time is None:
            update_time = datetime.datetime.utcnow().isoformat()

        content = ET.SubElement(entry, "content")
        author  = ET.SubElement(entry, "author")
        name    = ET.SubElement(author, "name")
        updated = ET.SubElement(entry, "updated")

        content.text = text
        name.text = author_name
        updated.text = update_time

        if in_reply_to is not None:
            irt = ET.SubElement(entry, "{{{}}}in-reply-to".format(ATOM_THR_NS), ref=in_reply_to)

        return entry

    def publish(self, text, author_name=None, in_reply_to=None):
        log.debug("Publishing to channel %s...", self.jid)
        entry = self._make_atom(text, author_name=author_name, in_reply_to=in_reply_to)
        node = "/user/{}/posts".format(self.jid)
        res = self.client.ps.publish(self.client.channels_jid, node, payload=entry)
        id_ = res["pubsub"]["publish"]["item"]["id"]
        log.info("Published to channel %s with id %s", self.jid, id_)
        return id_

    def retract(self, id_):
        log.debug("Retracting %s from channel %s", id_, self.jid)
        node = "/user/{}/posts".format(self.jid)
        self.client.ps.retract(self.client.channels_jid, node, id_, notify=True)

    def set_status(self, text, author_name=None):
        log.debug("Setting status for channel %s...", self.jid)
        entry = self._make_atom(text, author_name=author_name)
        node = "/user/{}/status".format(self.jid)
        res = self.client.ps.publish(self.client.channels_jid, node, payload=entry)
        id_ = res["pubsub"]["publish"]["item"]["id"]
        log.info("Status set for channel %s with id %s", self.jid, id_)
        return id_

    def update_config(self, **kwds):
        # Create config form
        form = self.client.data_forms.make_form(ftype="submit")
        form.add_field(var="FORM_TYPE", ftype="hidden", value="http://jabber.org/protocol/pubsub#node_config")
        for (dk, ik) in self.CONFIG_MAP:
            if dk in kwds:
                form.add_field(var=ik, value=kwds[dk])

        log.info("Updating config for channel %s", self.jid)
        node = "/user/{}/posts".format(self.jid)
        self.client.ps.set_node_config(self.client.channels_jid, node, form)
    # }}}
# }}}
# Local Variables:
# mode: python3
# End:
