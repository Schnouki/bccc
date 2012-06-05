bccc
====

Welcome to bccc, the **b**uddy**c**loud **c**onsole **c**lient.

Screenshot
----------

They say it's worth a thousand words, so here it is.

![Screenshot](http://i.imgur.com/35x39.png)

There's even a [screencast on YouTube](http://youtu.be/vi1nyCPDGTk).


Installation
------------

bccc is written in [Python 3](http://python.org/download/releases/), and is
known to work with Python 3.1 and 3.2. It probably won't work with previous
versions of Python 3, and it definitely won't work with Python 2.

bccc uses the following libraries:

- [Urwid](http://pypi.python.org/pypi/urwid), a console user interface library
  (tested with v1.0.1)
- [SleekXMPP](http://pypi.python.org/pypi/sleekxmpp), a library for XMPP (tested
  with v1.0)
- [dateutil](http://pypi.python.org/pypi/python-dateutil), everything you need
  for manipulating dates and times in Python (tested with v2.0)
- [dnspython3](http://pypi.python.org/pypi/dnspython3/), a DNS toolkit (optional)

You can install them using [pip3](http://www.pip-installer.org/) (`python-pip`
package in Arch Linux) or `easy_install3` (`python3-setuptools` package in
Debian/Ubuntu):

    # Global installation (in /usr or /usr/local):
    sudo pip3 install urwid sleekxmpp python-dateutil dnspython3
    # or
    sudo easy_install3 urwid sleekxmpp python-dateutil dnspython3

    # User installation (in $HOME):
    pip3 install --user urwid sleekxmpp python-dateutil dnspython3
    # or
    sudo easy_install3 --user urwid sleekxmpp python-dateutil dnspython3

(If you're using Debian/Ubuntu, you will need to install `python3-dev` and `gcc`
first.)

If you use [Arch Linux](http://archlinux.org/), you're awesome! And if you have
installed [yaourt](https://aur.archlinux.org/packages.php?ID=5863) (or any other
AUR helper), you can install all of these with the following command:

    yaourt -S python-{urwid,sleekxmpp-git,dateutil,dnspython}

After doing all of this, you can install bccc from its Git repository:

    git clone git://github.com/Schnouki/bccc.git
    cd bccc
    python3 setup.py build

    # Global installation (in /usr or /usr/local):
    sudo python3 setup.py install
    # User installation (in $HOME):
    python3 setup.py install --user

If you want to hack on bccc, you should install it with `develop`. It will be
installed globally, but will still use the files in your Git checkout, making it
easier to test your changes:

    # Global "develop" installation (in /usr or /usr/local):
    sudo python3 setup.py develop
    # User "develop" installation (in $HOME):
    python3 setup.py develop --user

If you installed bccc with `--user`, you must add `$HOME/.local/bin` to your
`$PATH`.

You should now be able to run bccc by just typing `bccc` in a terminal emulator.
If it complain about a missing configuration file, congratulations, your
installation probably works `:)`


### Uninstall

If you don't like bccc, you can uninstall it with pip3:

    pip3 uninstall bccc

There may be some leftover files after that if you did a `--user` or `develop`
install: `$HOME/.local/bin/bccc` and `/usr/bin/bccc`. You will have to remove
them by hand.

At the moment `easy_install` does not seem to be capable of uninstalling
modules. So if `pip3` is not available on your platform (and can't be installed
with `easy_install3 pip`), you will have to uninstall bccc by hand. On my
computer I can do it with these commands (as root):

    rm /usr/lib/python3.2/site-packages/bccc*
    rm /usr/bin/bccc
    nano /usr/lib/python3.2/site-packages/easy-install.pth
    # remove bccc lines in easy-install.pth

You will probably have to adapt them on your system, for example by using
`/usr/local` instead of `/usr`.


### Troubleshooting

When using `easy_install3` or some old versions of setuptools or distribute,
`bccc` won't run but will fail with the following message:

    Traceback (most recent call last):
      File "/usr/local/bin/bccc", line 7, in <module>
        execfile(__file__)
    NameError: name 'execfile' is not defined

This is due to these versions of setuptools/distribute not being correctly
updated for Python 3, where the `execfile` function is no longer available.

To fix it, edit your `/usr/local/bin/bccc` file and replace the
`execfile(__file)` line with the following one:

    exec(compile(open(__file__).read(), __file__, 'exec'))


Configuration
-------------

Before being able to use bccc, you will need to write a configuration file. The
easiest way to do so is actually to run bccc: if no configuration file is found,
it will ask for your credentials and create a configuration file using the
default one.

If you want to write the configuration file by hand, a good sample is available
in the Git repository, in `bccc/bccc.conf.sample`. You should copy it to
`~/.config/bccc/bccc.conf`, make sure it is only readable by you (`chmod 600
~/.config/bccc/bccc.conf`), and edit it to adjust your login and password.

This configuration file also contains the full palette used to render the UI.
The values in the sample file work well for a dark terminal (see screenshot),
but will need some adjustment if you use a light background. In particular you
will need to change "post text", "reply text" and their "focused" counterparts
to dark colors ("black", "black,bold"), as well as the status bar.


Basic usage
-----------

- Use the arrow keys to navigate through the interface.
- Channels are displayed in the sidebar on the left, and their content in the
  main panel on the right.
- Channels are sorted by the date of the most recent item in the channel, i.e.
  most recently updated channels first. Your personal channel will always be the
  first one at the top.
- The info bar (top of the main panel) has information about the active channel.
- The status bar (bottom of the screen) displays relevant messages and can be
  used for some inputs (see below).

---

- When the sidebar is focused, you can browse through your subscribed channels.
  Press `Enter` to select one and display it in the main panel.
- You can go to an arbitrary channel by pressing `g` and typing the name of the
  channel. When a post or reply in the main panel is focused, you can press `G`
  to go to the author's channel. If you're not subscribed to this channel, its
  current content will be displayed *but it won't update automatically as new
  content is posted*.

---

- In the main panel, you can start writing a new post by pressing `n`, or you
  can start replying to the focused post/reply by pressing `r`. After you have
  typed your message, press `Alt+Enter` to send it or `Escape` to cancel.
- In the main panel, you can press `=` to force reloading the channel. This is
  mostly useful when debugging, not for general usage `:)`
- In the main panel, you can update the active channel title, status message and
  description by typing `t`, `s` or `d`.
- If the focused post/reply contain URLs, you can open them in your browser by
  pressing `o`. This is especially useful for URLs longer than one line (other
  URLs may be handled correctly by your terminal emulator).
- You can delete the focused post/reply with the `delete` key.

---

Posts and replies in the active channel are grouped by thread: first the post,
then its replies in chronological order. Most recently updated threads are
listed first.

When new content is posted to the active channel, the corresponding thread will
be moved to the top, so in case of a new post you may have to scroll to see it.
*This behavior may change in the future.*

When new content is posted to an inactive channel, the channel will be moved to
the top of the sidebar and the number of unread items will be displayed next to
the channel name.


TODO
----

- get PubSub notifications for unsubscribed channels displayed with `g`/`G`
- better handling of Atom elements: should be done in SleekXMPP by registering
  new stanza types
- handle errors: private channels, posting forbidden, etc.
- handle subscriptions, affiliations, moderators, etc.
- persistence: save last known item ID for each channel in a database and tell
  how many new items there are after a relaunch

*Patches welcome!* `:)`


Hacking
-------

bccc is free software, available under the terms of the
[Apache License, version 2.0](https://www.apache.org/licenses/LICENSE-2.0). You
are encouraged to redistribute and modify it as you need. If you wish to
contribute to it (by reporting bugs, writing doc or submitting patches), the
easiest way is to use the [GitHub page](https://github.com/Schnouki/bccc).


Contact
-------

If you need help setting up, using or hacking bccc, feel free to contact me:

- on buddycloud: my channel is `schnouki@pouet.im`
- in the [buddycloud chatroom](https://www.jappix.com/?r=seehaus@channels.buddycloud.com)
- by [mail](mailto:schnouki--AT--schnouki--DOT--net)
- on [GitHub](https://github.com/Schnouki/)
