# Copyright (c) 2010-2011 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
import hashlib
import os
import shutil
from slogging import common
import sqlite3

from swift.account.backend import AccountBroker
from swift.account.server import DATADIR as account_server_data_dir
from swift.common.constraints import check_mount
from swift.common.daemon import Daemon
from swift.common import utils
from swift.container.backend import ContainerBroker
from swift.container.server import DATADIR as container_server_data_dir

import time
from tzlocal import get_localzone
import urllib


local_zone = get_localzone()


class DatabaseStatsCollector(Daemon):
    """DatabaseStatsCollector class.

    Extract storage stats from account databases on the
    account storage nodes.

    Any subclasses must define the function get_data.
    """
    def __init__(self, stats_conf, stats_type, data_dir, filename_format):
        super(DatabaseStatsCollector, self).__init__(stats_conf)
        self.stats_type = stats_type
        self.data_dir = data_dir
        self.filename_format = filename_format
        self.devices = stats_conf.get('devices', '/srv/node')
        self.mount_check = stats_conf.get('mount_check',
                                          'true').lower() in utils.TRUE_VALUES
        self.target_dir = stats_conf.get('log_dir', '/var/log/swift')
        utils.mkdirs(self.target_dir)
        self.logger = utils.get_logger(stats_conf,
                                       log_route='%s-stats' % stats_type)
        self.time_zone = common.get_time_zone(stats_conf, self.logger,
                                              'time_zone', str(local_zone))

    def run_once(self, *args, **kwargs):
        self.logger.info(_("Gathering %s stats") % self.stats_type)
        start = time.time()
        self.find_and_process()

        msg = _("Gathering %(stats_type)s stats complete "
                "(%(time)0.2f minutes)") % {'stats_type': self.stats_type,
                                            'time': (time.time() - start) / 60}
        self.logger.info(msg)

    def get_data(self):
        raise NotImplementedError('Subclasses must override')

    def get_header(self):
        raise NotImplementedError('Subclasses must override')

    def find_and_process(self):
        src_filename = datetime.now(self.time_zone).strftime(
            self.filename_format)
        working_dir = os.path.join(self.target_dir,
                                   '.%-stats_tmp' % self.stats_type)
        shutil.rmtree(working_dir, ignore_errors=True)
        utils.mkdirs(working_dir)
        tmp_filename = os.path.join(working_dir, src_filename)
        hasher = hashlib.md5()
        try:
            with open(tmp_filename, 'wb') as statfile:
                statfile.write(self.get_header())
                for device in os.listdir(self.devices):
                    if self.mount_check and not check_mount(self.devices,
                                                            device):
                        self.logger.error(
                            _("Device %s is not mounted, skipping.") % device)
                        continue
                    db_dir = os.path.join(self.devices, device, self.data_dir)
                    if not os.path.exists(db_dir):
                        self.logger.debug(
                            _("Path %s does not exist, skipping.") % db_dir)
                        continue
                    for root, dirs, files in os.walk(db_dir, topdown=False):
                        for filename in files:
                            if filename.endswith('.db'):
                                db_path = os.path.join(root, filename)
                                try:
                                    line_data = self.get_data(db_path)
                                except sqlite3.Error as err:
                                    values = {'db_path': db_path, 'err': err}
                                    msg = _("Error accessing db "
                                            "%(db_path)s: %(err)s") % values
                                    self.logger.info(msg)
                                    continue
                                if line_data:
                                    statfile.write(line_data)
                                    hasher.update(line_data)

            src_filename += hasher.hexdigest()
            utils.renamer(tmp_filename,
                          os.path.join(self.target_dir, src_filename))
        finally:
            shutil.rmtree(working_dir, ignore_errors=True)


class AccountStatsCollector(DatabaseStatsCollector):
    """AccountStatsCollector class.

    Extract storage stats from account databases on the account
    storage nodes
    """
    def __init__(self, stats_conf):
        super(AccountStatsCollector, self).__init__(stats_conf, 'account',
                                                    account_server_data_dir,
                                                    'stats-%Y%m%d%H_')

    def get_data(self, db_path):
        """Data for generated csv has the following columns:

        Account Hash, Container Count, Object Count, Bytes Used

        :raises sqlite3.Error: does not catch errors connecting to db
        """
        line_data = None
        broker = AccountBroker(db_path)
        if not broker.is_deleted():
            info = broker.get_info()
            line_data = '"%s",%d,%d,%d\n' % (info['account'],
                                             info['container_count'],
                                             info['object_count'],
                                             info['bytes_used'])
        return line_data

    def get_header(self):
        return ''


class ContainerStatsCollector(DatabaseStatsCollector):
    """ContainerStatsCollector class

    Extract storage stats from container databases on the container
    storage nodes
    """
    def __init__(self, stats_conf):
        super(ContainerStatsCollector, self).__init__(
            stats_conf, 'container',
            container_server_data_dir,
            'container-stats-%Y%m%d%H_')
        # webob calls title on all the header keys
        self.metadata_keys = [
            'X-Container-Meta-%s' % mkey.strip().title()
            for mkey in stats_conf.get('metadata_keys', '').split(',')
            if mkey.strip()]

    def get_header(self):
        header = 'Account Hash,Container Name,Object Count,Bytes Used'
        if self.metadata_keys:
            xtra_headers = ','.join(self.metadata_keys)
            header += ',%s' % xtra_headers
        header += '\n'
        return header

    def get_data(self, db_path):
        """Data for generated csv has the following columns:

        Account Hash, Container Name, Object Count, Bytes Used

        This will just collect whether or not the metadata is set
        using a 1 or ''.

        :raises sqlite3.Error: does not catch errors connecting to db
        """
        line_data = None
        broker = ContainerBroker(db_path)
        if not broker.is_deleted():
            info = broker.get_info()
            encoded_container_name = urllib.quote(info['container'])
            line_data = '"%s","%s",%d,%d' % (
                info['account'], encoded_container_name,
                info['object_count'], info['bytes_used'])
            if self.metadata_keys:
                metadata_results = ','.join(
                    [broker.metadata.get(mkey) and '1' or ''
                     for mkey in self.metadata_keys])
                line_data += ',%s' % metadata_results
            line_data += '\n'
        return line_data
