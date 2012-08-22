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

import dateutil.tz
import urwid

from .util import BoxedEdit

# {{{ Basic item widget
class ItemWidget(urwid.FlowWidget):
    attr_author = ("post author", "focused post author")
    attr_date   = ("post date", "focused post date")
    attr_text   = ("post text", "focused post text")

    def __init__(self, id=None, author="", date="", text="", padding=0):
        self._id = id
        self._author = author
        self._date = date
        self._text = text

        # Init sub-widgets
        author_w = urwid.Text((" "*padding) + author, wrap="clip")
        author_w = urwid.AttrMap(author_w, *self.attr_author)

        date_w = urwid.Text(date, align="right", wrap="clip")
        date_w = urwid.AttrMap(date_w, *self.attr_date)

        text_w = urwid.Text(text)
        text_w = urwid.Padding(text_w, left=4+padding, right=1)
        text_w = urwid.AttrMap(text_w, *self.attr_text)

        self.widgets = (author_w, date_w, text_w)
        urwid.FlowWidget.__init__(self)
        self._selectable = True

    @property
    def id(self): return self._id

    @property
    def author(self): return self._author

    @property
    def date(self): return self._date

    @property
    def text(self): return self._text

    @property
    def tombstone(self): return False

    def keypress(self, size, key):
        return key

    def rows(self, size, focus=False):
        return self.widgets[2].rows(size, focus) + 1

    def render(self, size, focus=False):
        maxcol = size[0]

        # Render first line
        author_col, _ = self.widgets[0].pack(focus=focus)
        date_col, _ = self.widgets[1].pack(focus=focus)
        canvas_head = None
        if author_col + date_col <= maxcol:
            # We can render them both!
            canvas_author = self.widgets[0].render((maxcol-date_col,), focus)
            canvas_date = self.widgets[1].render((date_col,), focus)
            canv = [
                (canvas_author, None, True, maxcol-date_col),
                (canvas_date,   None, True, date_col),
            ]
            canvas_head = urwid.CanvasJoin(canv)
        else:
            # Only render author
            canvas_head = self.widgets[0].render(size, focus)

        # Render text
        canvas_text = self.widgets[2].render(size, focus)

        canv = [
            (canvas_head, None, True),
            (canvas_text, None, True),
        ]
        out = urwid.CanvasCombine(canv)
        return out
# }}}
# {{{ Single post/reply widget
class PostWidget(ItemWidget):
    def __init__(self, post, padding=0):
        self._item = post

        author = "[deleted]"
        text = "[deleted]"
        date = post.published.astimezone(dateutil.tz.tzlocal()).strftime("%x - %X")
        if not post.tombstone:
            author = post.author
            text = post.content

        ItemWidget.__init__(self, post.id, author, date, text, padding)

    @property
    def item(self): return self._item

    @property
    def tombstone(self): return self._item.tombstone

class ReplyWidget(PostWidget):
    attr_author = ("reply author", "focused reply author")
    attr_date   = ("reply date", "focused reply date")
    attr_text   = ("reply text", "focused reply text")

    def __init__(self, reply):
        PostWidget.__init__(self, reply, padding=2)
        self._in_reply_to = reply.in_reply_to

    @property
    def in_reply_to(self): return self._in_reply_to

    def __lt__(self, other):
        return self.item.published < other.item.published

    def __eq__(self, other):
        return type(other) is ReplyWidget and self.id == other.id

    def __hash__(self):
        return object.__hash__(self)
# }}}
# {{{ New post/reply composition widgets
class NewPostWidget(BoxedEdit):
    attr_edit = ("new post text", "focused new post text")
    attr_box  = ("new post box",  "focused new post box")
    box_title = "New post"
    status_base = "New post in {}"

    def __init__(self, ui, channel):
        self.ui = ui
        self.channel = channel
        super().__init__()

    def update(self):
        msg = self.status_base.format(self.channel.jid)
        msg += " - {} characters".format(len(self.edit.edit_text))
        msg += " [Alt+Enter to post, Escape to cancel and discard]"
        self.ui.status.set_text(msg)

    def validate(self, *args, **kwds):
        text = self.edit.edit_text.strip()
        if len(text) > 0:
            self.channel.publish(text, *args, **kwds)
        self.ui.threads_list.cancel_new_item()

    def cancel(self):
        self.ui.threads_list.cancel_new_item()

class NewReplyWidget(NewPostWidget):
    attr_edit = ("new reply text", "focused new reply text")
    attr_box  = ("new reply box",  "focused new reply box")
    box_title = "New reply"
    status_base = "New reply in {}"

    def __init__(self, ui, channel, thread_id):
        self.thread_id = thread_id
        super().__init__(ui, channel)

    def validate(self, *args, **kwds):
        return super().validate(*args, in_reply_to=self.thread_id, **kwds)
# }}}
# {{{ Edit post/reply widgets
class EditItemWidget(NewPostWidget):
    def __init__(self, ui, channel, text, author, id_, thread_id=None):
        self.orig_text = text
        self.orig_author = author
        self.orig_id = id_
        self.orig_thread_id = thread_id
        super().__init__(ui, channel)

        self.edit.set_edit_text(self.orig_text)

    def validate(self, *args, **kwds):
        return super().validate(*args, author_name=self.orig_author, id_=self.orig_id, in_reply_to=self.orig_thread_id, **kwds)

class EditPostWidget(EditItemWidget):
    attr_edit = ("new post text", "focused new post text")
    attr_box  = ("new post box",  "focused new post box")
    box_title = "Edit post"
    status_base = "Edit post in {}"

class EditReplyWidget(EditItemWidget):
    attr_edit = ("new reply text", "focused new reply text")
    attr_box  = ("new reply box",  "focused new reply box")
    box_title = "Edit reply"
    status_base = "Edit reply in {}"

# }}}
# Local Variables:
# mode: python3
# End:
