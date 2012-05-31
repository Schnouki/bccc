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
import re

import urwid

logger = logging.getLogger('bccc.ui.util')
logger.addHandler(logging.NullHandler())

# {{{ Timezone
# From http://docs.python.org/py3k/library/datetime.html#tzinfo-objects
import datetime
import time

STDOFFSET = datetime.timedelta(seconds = -time.timezone)
if time.daylight:
    DSTOFFSET = datetime.timedelta(seconds = -time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET

class LocalTimezone(datetime.tzinfo):
    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def dst(self, dt):
        if self._isdst(dt):
            return DSTDIFF
        else:
            return datetime.timedelta(0)

    def tzname(self, dt):
        return time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, 0)
        # FIXME: workaround for #9. There will still be an OverflowError for
        # year > 2038 on i686 :/
        stamp = 0
        try:
            stamp = time.mktime(tt)
        except OverflowError:
            logger.debug("OverflowError in LocalTimezone._isdst(), tt=" + str(tt))
        tt = time.localtime(stamp)
        return tt.tm_isdst > 0

LocalTZ = LocalTimezone()
OldestDate = datetime.datetime.fromtimestamp(0, tz=LocalTZ)
# }}}
# {{{ Boxed edit widget
class BoxedEdit(urwid.AttrMap):
    attr_edit = ("boxed edit text", "focused boxed edit text")
    attr_box  = ("bodex edit box",  "focused boxed edit box")
    box_title = "Boxed edit"

    def __init__(self):
        self.edit = urwid.Edit(multiline=True)
        edit_am = urwid.AttrMap(self.edit, *self.attr_edit)

        linebox = urwid.LineBox(edit_am, self.box_title)
        super().__init__(linebox, *self.attr_box)

        self.update()

    def keypress(self, size, key):
        keyret = super().keypress(size, key)
        self.update()
        if keyret == "meta enter":
            self.validate()
        elif keyret == "esc":
            self.cancel()
        else:
            return keyret

    def update(self):
        pass

    def validate(self):
        pass

    def cancel(self):
        pass
# }}}
# {{{ Status bar that can act as an input box
class SmartStatusBar(urwid.WidgetWrap):
    def __init__(self):
        self._frm = None

        self._txt = urwid.Text("")
        self._txt_am = urwid.AttrMap(self._txt, "status bar")

        self._edit = urwid.Edit()
        self._edit_am = urwid.AttrMap(self._edit, "status bar input")
        self._edit_callback = None

        super().__init__(self._txt_am)

    def set_frame(self, frm):
        self._frm = frm

    def set_text(self, txt):
        return self._txt.set_text(txt)

    def ask(self, caption, callback):
        self._edit.set_caption(("status bar question", caption))
        self._edit.edit_text = ""
        self._edit_callback = callback
        self._w = self._edit_am
        self._frm.set_focus("footer")

    def _restore_text(self):
        self._frm.set_focus("body")
        self._w = self._txt_am

    def keypress(self, size, key):
        if key == "enter":
            self._edit_callback(self._edit.edit_text)
            self._restore_text()
        elif key == "esc":
            self._restore_text()
        else:
            return super().keypress(size, key)
# }}}
# {{{ URLs extractor
# From http://daringfireball.net/2010/07/improved_regex_for_matching_urls
URL_RE = re.compile(r"""(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’]))""")
URL_PROTOPART_RE = re.compile(r"""(?i)^[a-z0-9-]+:""")

def extract_urls(txt):
    for m in URL_RE.finditer(txt):
        url = m.group(1)

        # Make sure it has a protocol part
        if URL_PROTOPART_RE.match(url) is None:
            url = "http://" + url

        yield url
# }}}

# Local Variables:
# mode: python3
# End:
