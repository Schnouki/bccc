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

import threading

import sleekxmpp
from sleekxmpp.exceptions import IqError
from sleekxmpp.xmlstream.matcher import StanzaPath
from sleekxmpp.xmlstream.handler import Callback

from bccc.client.channel import Channel

# {{{ Exceptions
class ClientError(Exception):
    """Error in a client operation"""
    pass
# }}}
# {{{ SleekXMPP extensions
from sleekxmpp.xmlstream import register_stanza_plugin
from sleekxmpp.plugins import xep_0059, xep_0060

register_stanza_plugin(xep_0060.stanza.pubsub.Pubsub, xep_0059.stanza.Set)
# }}}
# {{{ Client
class Client(sleekxmpp.ClientXMPP):
    """The main buddycloud client"""

    # {{{ Init, login, discovery, etc.
    def __init__(self, jid, password):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)

        self.channels_cond = threading.Condition()
        self.channels_jid = None
        self.channels = {}

        self.register_plugin("xep_0004") # Data forms
        self.register_plugin("xep_0030") # Service Discovery
        self.register_plugin("xep_0059") # Result Set Management
        self.register_plugin("xep_0060") # PubSub
        self.register_plugin("xep_0199") # XMPP Ping

        # Easier access to server features
        self.data_forms = self["xep_0004"]
        self.disco = self["xep_0030"]
        self.ps = self["xep_0060"]

        # PubSub handler
        self.register_handler(
            Callback("Pubsub event",
                     StanzaPath("message/pubsub_event"),
                     self.handle_pubsub_event))

        self.add_event_handler("session_start", self.start)

    def __repr__(self):
        return "<bccc.client.Client {}>".format(self.boundjid.bare)

    def start(self, event):
        # Try to find channels service
        items = self.disco.get_items(jid=self.boundjid.host, block=True)

        for jid, node, name in items["disco_items"]["items"]:
            try:
                info = self.disco.get_info(jid=jid, block=True)
            except IqError:
                continue
            for id_ in info["disco_info"]["identities"]:
                if id_[0] == "pubsub" and id_[1] == "channels":
                    with self.channels_cond:
                        self.channels_jid = jid
                        self.channels_cond.notify()

                    # First send a presence
                    self.send_presence(pto=jid, pfrom=self.boundjid.full,
                                       pstatus="buddycloud", pshow="na", ppriority=-1)

                    # In-band registration. XEP 0077 says we SHOULD send a "get"
                    # first, but not having a plugin do it for us is troublesome
                    # enough :)
                    iq = self.make_iq(ito=jid, itype="set", iquery="jabber:iq:register")
                    res = iq.send(block=True)
                    if "error" in res:
                        raise ClientError("Could not register with channels service: {}".format(res["errors"]))

                    break

        if self.channels_jid is None:
            raise ClientError("No channels service found.")
    # }}}
    # {{{ Channels management
    def get_channels(self):
        """ Get subscribed channels (synchronously)"""
        # TODO: make that asynchronous! (but handling user's channel will be tricky)
        # Wait for the channels JID to be available
        with self.channels_cond:
            while self.channels_jid is None:
                self.channels_cond.wait()

        channels = []
        subnode = "/user/" + self.boundjid.bare + "/subscriptions"
        items = self.ps.get_items(self.channels_jid, subnode, block=True)
        for item in items["pubsub"]["items"]:
            chan = self.get_channel(item["id"])
            channels.append(chan)
        return channels

    def get_channel(self, jid, force_new=False):
        if jid in self.channels and not force_new:
            return self.channels[jid]

        if self.channels_jid is None:
            raise ClientError("Channels service is not ready yet")

        chan = Channel(self, jid)
        self.channels[jid] = chan
        return chan
    # }}}
    # {{{ PubSub handling
    def handle_pubsub_event(self, msg):
        evt = msg["pubsub_event"]

        EVENT_POST = 1
        EVENT_STATUS = 2
        EVENT_CONFIG = 3

        # Data about the event
        evt_type, data, jid = None, None, None

        if "items" in evt.keys():
            items = evt["items"]
            node = items["node"]
            if not node.startswith("/user/"):
                return

            jid, chan_type = node[6:].rsplit("/", 1)

            if chan_type == "posts":
                evt_type = EVENT_POST
            elif chan_type == "status":
                evt_type = EVENT_STATUS
            else:
                return
            data = [item.get_payload() for item in items]

        elif "configuration" in evt.keys():
            evt_type = EVENT_CONFIG
            data = evt["configuration"]
            node = data["node"]
            jid, chan_type = node[6:].rsplit("/", 1)
            if chan_type != "posts":
                return

        # Do we have everything we need?
        if evt_type is None or data is None or jid is None:
            return

        # Now route event to the right channel
        chan = self.get_channel(jid)

        if evt_type == EVENT_POST:
            chan.handle_post_event(data)
        elif evt_type == EVENT_STATUS:
            chan.handle_status_event(data)
        elif evt_type == EVENT_CONFIG:
            chan.handle_config_event(data)
    # }}}
# }}}

# Local Variables:
# mode: python3
# End:
