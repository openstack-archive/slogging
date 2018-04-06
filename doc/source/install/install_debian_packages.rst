===================================
How to Install with Debian Packages
===================================

#. Install Debian Package::

    sudo dpkg -i python-slogging_[slogging-version]_all.deb

#. You can ignore following kind of error messages.::

    dpkg: dependency problems prevent configuration of python-slogging:
     python-slogging depends on python-pbr; however:
      Package python-pbr is not installed.
     python-slogging depends on python-iptools; however:
      Package python-iptools is not installed.
     python-slogging depends on python-tzlocal; however:
      Package python-tzlocal is not installed.
     python-slogging depends on python-swift; however:
      Package python-swift is not installed.

    dpkg: error processing package python-slogging (--install):
     dependency problems - leaving unconfigured
    Errors were encountered while processing:
     python-slogging

#. Check if the Debian Package has successfully installed::

    dpkg -l | grep slogging

#. After install Debian packages, you need to install following dependent packages::

    pbr
    iptools
    tzlocal
    swift

- You can install Swift by `SAIO - Swift All In One <https://docs.openstack.org/swift/latest/development_saio.html>`_.
- You can install pbr, iptools, tzlocal by pip command like::

    pip install [package_name]

