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
import logging
import weakref

import dateutil.parser

logger = logging.getLogger('bccc.client.atom')
logger.addHandler(logging.NullHandler())

ATOM_NS     = "http://www.w3.org/2005/Atom"
ATOM_THR_NS = "http://purl.org/syndication/thread/1.0"
AS_NS       = "http://activitystrea.ms/spec/1.0/"


# {{{ Exceptions
class AtomError(Exception):
    """Error when handling an Atom"""
    pass
# }}}
# {{{ Atom element
class Atom:
    """Basic class for easier handling of Atom elements"""

    def __init__(self, elt):
        self.elt = elt

    def get_child(self, tag, ns=ATOM_NS):
        return self.elt.find("{{{}}}{}".format(ns, tag))

    @property
    def author(self):
        a = self.get_child("author")
        if a is None:
            # Something is terribly wrong.
            logger.warning("Atom without author")
            return "[unknown author]"
        name = a.find("{{{}}}name".format(ATOM_NS))
        if name is not None:
            return name.text
        else:
            # This should NOT happen >:-(
            url = a.find("{{{}}}url".format(ATOM_NS))
            if url is not None:
                logger.warning("Atom without author name")
                return url.text
            else:
                logger.warning("Atom without author name & URL")
                # Really ??!?
                return "[unknown author]"

    @property
    def content(self):
        cnt = self.get_child("content")
        if cnt is None:
            logger.warning("Atom without content")
            return ""
        text = self.get_child("content").text
        if text is None:
            logger.warning("Atom without content text")
            text = ""
        return text.strip()

    @property
    def id(self): return self.get_child("id").text

    @property
    def in_reply_to(self): return self.get_child("in-reply-to", ATOM_THR_NS).attrib["ref"]

    @property
    def link(self): return self.get_child("link").attrib

    @property
    def object_type(self):
        o = self.get_child("object", AS_NS)
        return o.find("{{{}}}object-type".format(AS_NS)).text

    @property
    def published(self):
        t = self.get_child("published").text
        return dateutil.parser.parse(t)

    @property
    def updated(self):
        t = self.get_child("updated").text
        return dateutil.parser.parse(t)

    @property
    def verb(self): return self.get_child("verb", AS_NS).text

    def __eq__(self, other):
        return type(other) is Atom and self.id == other.id

    def __lt__(self, other):
        return self.published > other.published # ">" to sort by newest first
# }}}
# {{{ Updatable Atoms list
class UpdatableAtomsList:
    """This behaves like a sorted list of Atoms that can be dynamically modified
    without invalidating its iterators. Items are sorted by newest first."""

    class iterator:
        def __init__(self, lst):
            self._list = lst
            self._idx = -1

        def __next__(self):
            self._idx += 1
            if self._idx < len(self._list):
                return self._list[self._idx]
            else:
                raise StopIteration

        def atoms_left(self):
            return len(self._list) - self._idx - 1

    def __init__(self):
        self._list = []
        self._iterators = weakref.WeakSet()

    def __iter__(self):
        it = UpdatableAtomsList.iterator(self)
        self._iterators.add(it)
        return it

    def __getitem__(self, idx):
        return self._list[idx]
    def __len__(self):
        return len(self._list)

    def __contains__(self, other):
        if type(other) is not Atom:
            return False
        for a in self._list:
            if a.id == other.id:
                return True
        return False

    def add(self, elt):
        a = Atom(elt)
        if a.object_type not in ("note", "comment"):
            raise AtomError("Unknown item type: {}".format(a.object_type))

        # Make sure this Atom is not already in the list
        if a in self:
            return

        # Find insertion position, and insert
        pos = bisect.bisect_left(self._list, a)
        self._list.insert(pos, a)

        # Update all iterators
        for it in self._iterators:
            if it._idx >= pos:
                it._idx += 1

        return a

    def remove(self, id_):
        # Find Atom with given id
        pos = None
        for (i, a) in enumerate(self._list):
            if a.id == id_:
                pos = i
                break
        if pos is None:
            return

        # Remove it and update all iterators
        del self._list[pos]
        for it in self._iterators:
            if it.idx >= pos:
                it.idx -= 1
# }}}

# {{{ Atom in SleekXMPP stanzas

# from sleekxmpp.xmlstream import register_stanza_plugin, ElementBase
# from sleekxmpp.plugins import xep_0059, xep_0060

# # {{{ Stanzas Atom & ActivityStreams
# class AtomEntry(ElementBase):
#     namespace = "http://www.w3.org/2005/Atom"
#     name = "entry"
#     plugin_attrib = name
#     interfaces = set(("author", "in_reply_to", "object", "verb"))
#     sub_interfaces = set(("content", "id", "link", "published", "updated"))

# class AtomAuthor(ElementBase):
#     namespace = "http://www.w3.org/2005/Atom"
#     name = "author"
#     plugin_attrib = name
#     sub_interfaces = set(("name", "url"))

#     def get_author(self):
#         auth = self._get_sub_text("name", default=None)
#         if auth is None: # This should not happen.
#             auth = self._get_sub_text("url", default=None)
#             if auth is None: # This should even less happen.
#                 auth = "[unknown author]"
#         return auth

# class AtomThrInReplyTo(ElementBase):
#     namespace = "http://purl.org/syndication/thread/1.0"
#     name = "in-reply-to"
#     plugin_attrib = name
#     interfaces = set(("ref",))

# class ActivityStreamsObject(ElementBase):
#     namespace = "http://activitystrea.ms/spec/1.0/"
#     name = "object"
#     plugin_attrib = name
#     sub_interfaces = set(("object-type",))

# class ActivityStreamsVerb(ElementBase):
#     namespace = "http://activitystrea.ms/spec/1.0/"
#     name = "verb"
#     plugin_attrib = verb
# # }}}


# register_stanza_plugin(xep_0060.stanza.pubsub.Item, AtomEntry)
# register_stanza_plugin(AtomEntry, AtomAuthor)
# register_stanza_plugin(AtomEntry, AtomThrInReplyTo)
# register_stanza_plugin(AtomEntry, ActivityStreamsObject)
# register_stanza_plugin(AtomEntry, ActivityStreamsVerb)

# }}}
# Local Variables:
# mode: python3
# End:
