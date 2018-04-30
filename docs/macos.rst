Mac OS Setup
============

Xcode
-----

The first step will be to determine if Xcode (Mac OS X's build tools) is installed.
Issue the following at the command prompt::

    $ xcode-select -p

If you see ``/Library/Developer/CommandLineTools``, you should be good to go.
In either case verify your build settings are working by doing::

    $ gcc

If you get something like ``clang: no input files``, you're fine. If you get a popup
window saying ``"gcc" command requires...``, go ahead and click **Install**.

Run the ``gcc`` command again::

    $ gcc --version


You are set, otherwise, run the following::

    $ xcode-select --install

A software update  popup window will appear, click **Install** and let it finish.

Homebrew
--------

`Homebrew <http://brew.sh/>`_ is the premier package manager missing from OS X, so let's fix that.

Following are the best steps for installing Homebrew (referred to hereafter as ``brew``)::

    $ sudo mkdir -p /usr/local
    $ sudo chown $(whoami):admin /usr/local
    $ cd /usr/local
    $ ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    $ brew doctor
    $ brew update
    $ mkdir -p ~/Library/LaunchAgents/

At this point, if setup was successful, your ``$PATH`` variable should correctly reference
``/usr/local/bin`` and ``/usr/local/sbin`` **before** ``/usr/bin`` and ``usr/sbin``.

Verify your ``$PATH``::

    $ echo $PATH

The following apps are used by various components in Python and other libs::

    $ brew install jpeg libpng libtiff libjpeg node pcre


Python
------

::

    $ brew install python3
    $ pip3 install -U setuptools pip



