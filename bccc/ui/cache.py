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
import logging
import os
import os.path
import shelve
import threading
import xml.etree.ElementTree as ET

import dateutil.tz

from bccc.client import Atom

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

class Cache:
    """Cache a channel and its content"""

    # {{{ Constructor and parameters
    cache_dir = os.path.join(os.getenv("XDG_CACHE_HOME", os.path.expanduser("~")), "bccc")
    max_items = 200
    defer_sec = 5
    never = datetime.datetime.fromtimestamp(0, tz=dateutil.tz.tzlocal())

    def __init__(self, loop, jid):
        self._jid = jid

        if not os.path.isdir(Cache.cache_dir):
            os.makedirs(Cache.cache_dir)
        self._fn = os.path.join(Cache.cache_dir, self._jid)
        self._db = shelve.open(self._fn)

        self._lock = threading.RLock()
        self._loop = loop
        self._handle = None
    # }}}
    # {{{ Sync handling
    def close(self):
        if self._handle is not None:
            self._loop.remove_alarm(self._handle)
            self._handle = None
        with self._lock:
            self._db.close()
            self._db = None

    def sync(self, *args):
        with self._lock:
            log.debug("Sync %s", self._jid)
            self._db.sync()

    def _defer_sync(self):
        if self._handle is not None:
            self._loop.remove_alarm(self._handle)
        self._handle = self._loop.set_alarm_in(Cache.defer_sec, self.sync)
    # }}}
    # {{{ Data conversion
    @staticmethod
    def _atom_to_entry(atom):
        upd = Cache.never
        try:
            upd = atom.updated
        except AttributeError:
            upd = atom.published
        xml = ET.tostring(atom.elt, encoding="unicode")
        return (upd, xml)

    @staticmethod
    def _entry_to_atom(entry):
        xml = entry[1]
        elt = ET.fromstring(xml)
        return Atom(elt)
    # }}}
    # {{{ Simple cached properties
    @property
    def mtime(self):
        with self._lock:
            if "mtime" in self._db:
                return self._db["mtime"]
            else:
                return Cache.never

    def _update(self):
        with self._lock:
            now = datetime.datetime.now(tz=dateutil.tz.tzlocal())
            self._db["mtime"] = now
            self._defer_sync()

    @property
    def config(self):
        with self._lock:
            if "config" in self._db:
                return self._db["config"]
            else:
                return {}
    @config.setter
    def config(self, conf):
        with self._lock:
            if "config" not in self._db or self._db["config"] != conf:
                self._db["config"] = conf
                self._update()

    @property
    def status(self):
        with self._lock:
            if "status" in self._db:
                return self._db["status"]
    @status.setter
    def status(self, val):
        with self._lock:
            if "status" not in self._db or self._db["status"] != val:
                self._db["status"] = val
                self._update()
    # }}}
    # {{{ Items handling
    @property
    def items(self):
        with self._lock:
            if "items" not in self._db:
                return []
            else:
                entries = [self._db["item-"+id] for id in self._db["items"]]
                atoms = [Cache._entry_to_atom(entry) for entry in entries]
                return atoms

    @property
    def last_update(self):
        with self._lock:
            if "items" in self._db:
                id = self._db["items"][0]
                entry = self._db["item-"+id]
                return entry[0]
            else:
                return Cache.never

    def add_item(self, atom):
        with self._lock:
            aid = atom.id
            entry = Cache._atom_to_entry(atom)

            if "items" not in self._db or len(self._db["items"]) == 0:
                self._db["items"] = [aid]
                self._db["item-"+aid] = entry
                self._update()
                return True

            ids = self._db["items"]
            # Is the item already in cache?
            if aid in ids:
                return False

            # Is the item too old to be in cache?
            if len(ids) >= Cache.max_items:
                oldest_entry = self._db["item-"+ids[-1]]
                if oldest_entry[0] > entry[0]:
                    return False

            # Insert new entry, preserving the order (newest items first)
            lo, hi = 0, len(ids)
            while lo < hi:
                mid = (lo+hi) // 2
                mid_entry = self._db["item-"+ids[mid]]
                if entry[0] >= mid_entry[0]: hi = mid
                else: lo = mid+1

            # Only insert if recent enough
            if lo < Cache.max_items:
                ids.insert(lo, aid)
                self._db["item-"+aid] = entry

                # Clean oldest items
                while len(ids) > Cache.max_items:
                    id = ids.pop()
                    del self._db["item-"+id]
                    changed = True

                self._db["items"] = ids
                self._update()
                return True
            else:
                return False
    # }}}
