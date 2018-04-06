=================================
How slogging process Swift's logs
=================================

This page shows you how slogging process logs on OpenStack Swift.

Log Processing plugins
~~~~~~~~~~~~~~~~~~~~~~

slogging is written to allow a plugin to be defined for
every log type.

slogging includes plugins for both access logs and storage stats logs.

Each plugin is responsible for defining, in a config section, where the logs
are stored on disk, where the logs will be stored in swift (account and
container), the filename format of the logs on disk, the location of the
plugin class definition, and any plugin-specific config values.

You need to define three methods for plugin.

- The ``constructor``. must accept one argument (the dict representation of the plugin's config section).
- The ``process`` method must accept an iterator, and the account, container, and object name of the log.
- The ``keylist_mapping`` accepts no parameters.

Actually, slogging collects following logs from Swift by using plugins.

Log Uploading
~~~~~~~~~~~~~

As a first step to collect stats data from Swift, you need to use ``swift-log-uploader``.
Basically there are three kind of logs.

- :ref:`Access Logs <access-logs>`
- :ref:`Account Logs <stats-logs>`
- :ref:`Container DB Stats Logs <stats-logs>`

You can pass plugin's name as argument of ``swift-log-uploader`` like following.::

    /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf access
    /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf stats
    /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf container-stats

You can set above command as cron job so that you can collect those kind of logs in regular basis.

``swift-log-uploader`` receive a config file and a plugin name(access,
container-stats, stats) through above settings.
Then it finds the log files on disk according to the plugin config section and
uploads them to the swift cluster as source data for :ref:`log-processing`.

This means one uploader process will run on each proxy server node and each
account server node.
To not upload partially-written log files, the uploader will not upload files
with an mtime of less than two hours ago.

.. _access-logs:

Access Logs
-----------

Access logs means the proxy server logs.

For example, a proxy request that is made on August 4, 2010 at 12:37 gets
logged in a file named 2010080412.

This allows easy log rotation and easy per-hour log processing.

To upload access logs, you can set cron like following::

    /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf access


.. _stats-logs:

Account / Container DB Stats Logs
---------------------------------

You can use ``swift-account-stats-logger`` and ``swift-container-stats-logger``
to collect Account / Container DB stats logs:

``swift-account-stats-logger`` runs on each account server (via cron) and
walks the filesystem looking for account databases. When an account database
is found, the logger selects the account hash, bytes_used, container_count,
and object_count. These values are then written out as one line in a csv file.

One csv file is produced for every run of ``swift-account-stats-logger``.
This means that, system wide, one csv file is produced for every storage node.
Rackspace runs the account stats logger every hour.

If you run account stats logger in every hour and if you have ten account servers,
ten csv files are produced every hour. Also, every account will have one
entry for every replica in the system. On average, there will be three copies
of each account in the aggregate of all account stat csv files created in one
system-wide run.

The ``swift-container-stats-logger`` runs in a similar fashion, scanning
the container dbs.

To upload account stats logs and container stats logs, you can set cron like following::

    /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf container-stats
    /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf stats

.. _log-processing:

Log Processing
~~~~~~~~~~~~~~

Log Processing is a kind of final process to create total stats data.

``swift-log-stats-collector`` accepts a config file and generates a csv
that is uploaded to swift.

It loads all plugins defined in the config file,
generates a list of all log files in swift that need to be processed,
and passes an iterable of the log file data to the appropriate plugin's
process method.
The process method returns a dictionary of data in the log file
keyed on (account, year, month, day, hour).
The ``log-stats-collector`` process then combines all dictionaries from
all calls to a process method into one dictionary.
Key collisions within each (account, year, month, day, hour) dictionary are
summed.
Finally, the summed dictionary is mapped to the final csv values with
each plugin's ``keylist_mapping`` method.

The resulting csv file has one line per (account, year, month, day, hour) for
all log files processed in that run of ``swift-log-stats-collector``.

