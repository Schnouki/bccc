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

        self.inbox_cond = threading.Condition()
        self.inbox_jid = None
        self.channels = {}

        self.register_plugin("xep_0004") # Data forms
        self.register_plugin("xep_0030") # Service Discovery
        self.register_plugin("xep_0059") # Result Set Management
        self.register_plugin("xep_0060") # PubSub
        self.register_plugin("xep_0077") # In-Band Registration
        self.register_plugin("xep_0199") # XMPP Ping

        # Easier access to server features
        self.data_forms = self["xep_0004"]
        self.disco = self["xep_0030"]
        self.ps = self["xep_0060"]

        self.add_event_handler("session_start", self.start)

        self.add_event_handler("pubsub_publish", self.handle_pubsub_publish)
        self.add_event_handler("pubsub_retract", self.handle_pubsub_retract)
        self.add_event_handler("pubsub_config", self.handle_pubsub_config)

    def __repr__(self):
        return "<bccc.client.Client {}>".format(self.boundjid.bare)

    def start(self, event):
        # Try to find inbox service
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
                elif id_[0] == "pubsub" and id_[1] == "inbox":
                    log.info("Inbox service found ad %s", jid)

                    # First send a presence
                    self.send_presence(pto=jid, pfrom=self.boundjid.full,
                                       pstatus="buddycloud", pshow="na", ppriority=-1)

                    # In-band registration. XEP 0077 says we SHOULD send a "get"
                    # first, it's easier this way :)
                    iq = self.make_iq_set(ito=jid)
                    iq.enable("register")
                    res = iq.send(block=True)
                    if "error" in res:
                        raise ClientError("Could not register with inbox: {}".format(res["errors"]))

                    # Then notify waiters
                    with self.inbox_cond:
                        self.inbox_jid = jid
                        self.inbox_cond.notify()

        if self.inbox_jid is None:
            raise ClientError("No inbox found.")

    def ready(self):
        # Wait until the client is ready and the inbox JID is available
        with self.inbox_cond:
            while self.inbox_jid is None:
                self.inbox_cond.wait()
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
    def handle_pubsub_publish(self, msg):
        evt = msg["pubsub_event"]
        items = evt["items"]
        node = items["node"]
        jid, chan_type = node[6:].rsplit("/", 1)

        if not node.startswith("/user/") or chan_type not in ("posts", "status"):
            log.debug("Publish event with unsupported node type: %s", node)
            return
        elif jid is None or len(jid) == 0:
            log.debug("Publish event with empty JID")
            return

        payload = items["item"]["payload"]
        chan = self.get_channel(jid)
        if chan_type == "posts":
            log.debug("Publish post event for %s: %s", jid, str(payload))
            chan.handle_post_event([payload])
        else:
            log.debug("Publish status event for %s: %s", jid, str(payload))
            chan.handle_status_event([payload])

    def handle_pubsub_retract(self, msg):
        evt = msg["pubsub_event"]
        items = evt["items"]
        node = items["node"]
        jid, chan_type = node[6:].rsplit("/", 1)

        if not node.startswith("/user/") or chan_type != "posts":
            log.debug("Retract event with unsupported node type: %s", node)
            return
        elif jid is None or len(jid) == 0:
            log.debug("Retract event with empty JID")
            return

        id = items["item"]["id"]
        chan = self.get_channel(jid)
        log.debug("Retract event for %s: %s", jid, id)
        chan.handle_retract_event([id])

    def handle_pubsub_config(self, msg):
        evt = msg["pubsub_event"]
        cfg = evt["configuration"]
        node = cfg["node"]
        jid, chan_type = node[6:].rsplit("/", 1)

        if not node.startswith("/user/") or chan_type != "posts":
            log.debug("Configuration event with unsupported node type: %s", node)
            return
        elif jid is None or len(jid) == 0:
            log.debug("Configuration event with empty JID")
            return

        chan = self.get_channel(jid)
        log.debug("Configuratio event for %s: %s", jid, cfg)
        chan.handle_config_event([cfg])
    # }}}
# }}}

# Local Variables:
# mode: python3
# End:
