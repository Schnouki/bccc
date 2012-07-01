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

import logging
import threading

import sleekxmpp
from sleekxmpp.exceptions import IqError
from sleekxmpp.xmlstream.matcher import StanzaPath
from sleekxmpp.xmlstream.handler import Callback

from bccc.client.channel import Channel

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

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
        log.info("Initializing SleekXMPP client")
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
        log.info("Starting service discovery")
        items = self.disco.get_items(jid=self.boundjid.host, block=True)

        for jid, node, name in items["disco_items"]["items"]:
            try:
                info = self.disco.get_info(jid=jid, block=True)
            except IqError:
                continue
            for id_ in info["disco_info"]["identities"]:
                if id_[0] == "pubsub" and id_[1] == "channels":
                    log.info("Channels service found at %s", jid)
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

    def ready(self):
        # Wait until the client is ready and the channels JID is available
        with self.channels_cond:
            while self.channels_jid is None:
                self.channels_cond.wait()
    # }}}
    # {{{ Channels management
    def get_channel(self, jid=None, force_new=False):
        self.ready()

        if jid is None:
            jid = self.boundjid.bare

        if jid in self.channels and not force_new:
            return self.channels[jid]

        chan = Channel(self, jid)
        self.channels[jid] = chan
        return chan
    # }}}
    # {{{ PubSub handling
    def handle_pubsub_event(self, msg):
        evt = msg["pubsub_event"]

        # The various events in this PubSub event
        items_event = {"post": [], "retract": [], "status": []}
        config_event = []

        # Target channel
        jid = None

        if "items" in evt.keys():
            items = evt["items"]
            if len(items) == 0:
                return

            node = items["node"]
            if not node.startswith("/user/"):
                return

            jid, chan_type = node[6:].rsplit("/", 1)

            if chan_type == "posts":
                for item in items:
                    typ = type(item)
                    if typ is xep_0060.stanza.pubsub_event.EventItem:
                        items_event["post"].append(item.get_payload())
                    elif typ is xep_0060.stanza.pubsub_event.EventRetract:
                        items_event["retract"].append(item["id"])
                    else:
                        log.error("Unsupported items type: %s", str(typ))
                        raise ClientError("Got PubSub event in posts channel with unknown items type")

            elif chan_type == "status":
                items_event["status"] = [item.get_payload() for item in items]

            else:
                log.debug("Unsupported node type for items event: %s", node)
                return

        if "configuration" in evt.keys():
            data = evt["configuration"]
            node = data["node"]
            jid, chan_type = node[6:].rsplit("/", 1)
            if chan_type != "posts":
                log.debug("Unsupported node type for configuration event: %s", node)
            else:
                config_event.append(data)

        # Do we have everything we need?
        if  jid is None:
            return

        # Now route event to the right channel
        chan = self.get_channel(jid)

        if len(items_event["retract"]) > 0:
            chan.handle_retract_event(items_event["retract"])
        if len(items_event["post"]) > 0:
            chan.handle_post_event(items_event["post"])
        if len(items_event["status"]) > 0:
            chan.handle_status_event(items_event["status"])
        if len(config_event) > 0:
            chan.handle_config_event(config_event)
    # }}}
# }}}

# Local Variables:
# mode: python3
# End:
