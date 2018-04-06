==============================================
Running the slogging on SAIO(Swift All In One)
==============================================

This page shows you how to install slogging on SAIO(Swift All In One)
environment.


#. Create a swift account to use for storing stats information, and note the
   account hash. The hash will be used in config files.

#. Edit ``/etc/rsyslog.d/10-swift.conf``::

    # Uncomment the following to have a log containing all logs together
    #local1,local2,local3,local4,local5.*   /var/log/swift/all.log

    $template HourlyProxyLog,"/var/log/swift/hourly/%$YEAR%%$MONTH%%$DAY%%$HOUR%"
    local1.*;local1.!notice ?HourlyProxyLog

    local1.*;local1.!notice /var/log/swift/proxy.log
    local1.notice           /var/log/swift/proxy.error
    local1.*                ~

#. Edit ``/etc/rsyslog.conf`` and make the following change::

    $PrivDropToGroup adm

#. ``mkdir -p /var/log/swift/hourly``
#. ``chown -R syslog.adm /var/log/swift``
#. ``chmod 775 /var/log/swift /var/log/swift/hourly``
#. ``service rsyslog restart``
#. ``usermod -a -G adm <your-user-name>``
#. Relogin to let the group change take effect.
#. Create ``/etc/swift/log-processor.conf``::

    [log-processor]
    swift_account = <your-stats-account-hash>
    user = <your-user-name>

    [log-processor-access]
    swift_account = <your-stats-account-hash>
    container_name = log_data
    log_dir = /var/log/swift/hourly/
    source_filename_pattern = ^
        (?P<year>[0-9]{4})
        (?P<month>[0-1][0-9])
        (?P<day>[0-3][0-9])
        (?P<hour>[0-2][0-9])
        .*$
    class_path = slogging.access_processor.AccessLogProcessor
    user = <your-user-name>

    [log-processor-stats]
    swift_account = <your-stats-account-hash>
    container_name = account_stats
    log_dir = /var/log/swift/stats/
    class_path = slogging.stats_processor.StatsLogProcessor
    devices = /srv/1/node
    mount_check = false
    user = <your-user-name>

    [log-processor-container-stats]
    swift_account = <your-stats-account-hash>
    container_name = container_stats
    log_dir = /var/log/swift/stats/
    class_path = slogging.stats_processor.StatsLogProcessor
    processable = false
    devices = /srv/1/node
    mount_check = false
    user = <your-user-name>

#. Add the following under [app:proxy-server] in ``/etc/swift/proxy-server.conf``::

    log_facility = LOG_LOCAL1

#. Create a ``cron`` job to run once per hour to create the stats logs. In
   ``/etc/cron.d/swift-stats-log-creator``::

    0 * * * * <your-user-name> /usr/local/bin/swift-account-stats-logger /etc/swift/log-processor.conf

#. Create a ``cron`` job to run once per hour to create the container stats logs. In
   ``/etc/cron.d/swift-container-stats-log-creator``::

    5 * * * * <your-user-name> /usr/local/bin/swift-container-stats-logger /etc/swift/log-processor.conf

#. Create a ``cron`` job to run once per hour to upload the stats logs. In
   ``/etc/cron.d/swift-stats-log-uploader``::

    10 * * * * <your-user-name> /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf stats

#. Create a ``cron`` job to run once per hour to upload the stats logs. In
   ``/etc/cron.d/swift-stats-log-uploader``::

    15 * * * * <your-user-name> /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf container-stats

#. Create a ``cron`` job to run once per hour to upload the access logs. In
   ``/etc/cron.d/swift-access-log-uploader``::

    5 * * * * <your-user-name> /usr/local/bin/swift-log-uploader /etc/swift/log-processor.conf access

#. Create a ``cron`` job to run once per hour to process the logs. In
   ``/etc/cron.d/swift-stats-processor``::

    30 * * * * <your-user-name> /usr/local/bin/swift-log-stats-collector /etc/swift/log-processor.conf

After running for a few hours, you should start to see .csv files in the
``log_processing_data`` container in the swift stats account that was created
earlier. This file will have one entry per account per hour for each account
with activity in that hour. One .csv file should be produced per hour. Note
that the stats will be delayed by at least two hours by default. This can be
changed with the ``new_log_cutoff`` variable in the config file. See
``log-processor.conf-sample`` for more details.
