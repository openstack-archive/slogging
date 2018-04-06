===============================
How to Build to Debian Packages
===============================

#. Make sure you have python-stdeb installed::

    sudo apt-get install python-stdeb

#. Also make sure pbr is installed as python package::

    pip install pbr

#. Then type following command at the top of slogging directory::

    python setup.py --command-packages=stdeb.command bdist_deb

#. Check if python-slogging package is successfully created::

    ls deb_dist/python-slogging-[slogging-version]*

