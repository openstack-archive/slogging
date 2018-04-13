============================
How to Build to RPM Packages
============================

#. Make sure you have rpm-build installed::

    sudo yum install rpm-build


Fedora/CentOS/RedHat
~~~~~~~~~~~~~~~~~~~~


#. Type following command at the top of slogging directory::

    sudo python setup.py bdist_rpm

#. Check if the RPM package has built::

    ls dist/slogging-[slogging-version]


OpenSUSE
~~~~~~~~

#. Type following command at the top of slogging directory::

    sudo zypper install rpm-build

#. Check if the RPM package has built::

    ls dist/slogging-[slogging-version]
