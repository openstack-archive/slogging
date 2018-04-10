============================
How to Build to RPM Packages
============================

#. Make sure you have rpm-build installed::

 - on Fedora/CentOS/RedHat::

    sudo yum install rpm-build

 - on OpenSUSE::

    sudo zypper install rpm-build

#. Thsn type following command at the top of slogging directory::

    sudo python setup.py bdist_rpm

#. Check if the RPM package has built::

    ls dist/slogging-[slogging-version]
