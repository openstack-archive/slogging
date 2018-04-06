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
import logging
import os
import random
from slogging import log_uploader
import string
from test.unit import temptree
import unittest

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger()

COMPRESSED_DATA = '\x1f\x8b\x08\x08\x87\xa5zM\x02\xffdata\x00KI,I\x04\x00c' \
                  '\xf3\xf3\xad\x04\x00\x00\x00'


PROXY_SERVER_CONF = os.environ.get('SWIFT_PROXY_TEST_CONFIG_FILE',
                                   '/etc/swift/proxy-server.conf')

access_regex = '''
    ^
    (?P<year>[0-9]{4})
    (?P<month>[0-1][0-9])
    (?P<day>[0-3][0-9])
    (?P<hour>[0-2][0-9])
    .*$
    '''


def mock_appconfig(*args, **kwargs):
    pass


class MockInternalProxy(object):

    def __init__(self, *args, **kwargs):
        pass

    def create_container(self, *args, **kwargs):
        return True

    def upload_file(self, *args, **kwargs):
        return True


_orig_LogUploader = log_uploader.LogUploader


class MockLogUploader(_orig_LogUploader):

    def __init__(self, conf, logger=LOGGER):
        conf['swift_account'] = conf.get('swift_account', '')
        conf['container_name'] = conf.get('container_name', '')
        conf['new_log_cutoff'] = conf.get('new_log_cutoff', '0')
        conf['source_filename_format'] = conf.get(
            'source_filename_format', conf.get('filename_format'))
        log_uploader.LogUploader.__init__(self, conf, 'plugin')
        self.logger = logger
        self.uploaded_files = []

    def upload_one_log(self, filename, year, month, day, hour):
        d = {'year': year, 'month': month, 'day': day, 'hour': hour}
        self.uploaded_files.append((filename, d))
        _orig_LogUploader.upload_one_log(self, filename, year, month,
                                         day, hour)


class ErrorLogUploader(MockLogUploader):

    def upload_one_log(self, filename, year, month, day, hour):
        raise OSError('foo bar')


class TestLogUploader(unittest.TestCase):

    def setUp(self):
        # mock internal proxy
        self._orig_InternalProxy = log_uploader.InternalProxy
        self._orig_appconfig = log_uploader.appconfig
        log_uploader.InternalProxy = MockInternalProxy
        log_uploader.appconfig = mock_appconfig

    def tearDown(self):
        log_uploader.appconfig = self._orig_appconfig
        log_uploader.InternalProxy = self._orig_InternalProxy

    def test_bad_upload(self):
        files = [datetime.now().strftime('%Y%m%d%H')]
        with temptree(files, contents=[COMPRESSED_DATA] * len(files)) as t:
            # invalid pattern
            conf = {'log_dir': t,
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': '%Y%m%d%h'}  # should be %H
            uploader = MockLogUploader(conf)
            self.assertRaises(SystemExit, uploader.upload_all_logs)

            conf = {'log_dir': t,
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': access_regex}
            uploader = ErrorLogUploader(conf)
            # this tests if the exception is handled
            uploader.upload_all_logs()

    def test_bad_pattern_in_config(self):
        files = [datetime.now().strftime('%Y%m%d%H')]
        with temptree(files, contents=[COMPRESSED_DATA] * len(files)) as t:
            # invalid pattern
            conf = {'log_dir': t,
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': '%Y%m%d%h'}  # should be %H
            uploader = MockLogUploader(conf)
            self.assertRaises(SystemExit, uploader.upload_all_logs)

            conf = {'log_dir': t,
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': access_regex}
            uploader = MockLogUploader(conf)
            uploader.upload_all_logs()
            self.assertEqual(len(uploader.uploaded_files), 1)

    def test_pattern_upload_all_logs(self):

        # test empty dir
        with temptree([]) as t:
            conf = {'log_dir': t,
                    'proxy_server_conf': PROXY_SERVER_CONF}
            uploader = MockLogUploader(conf)
            self.assertRaises(SystemExit, uploader.run_once)

        def get_random_length_str(max_len=10, chars=string.ascii_letters):
            return ''.join(random.choice(chars) for x in
                           range(random.randint(1, max_len)))

        template = 'prefix_%(random)s_%(digits)s.blah.' \
                   '%(datestr)s%(hour)0.2d00-%(next_hour)0.2d00-%(number)s.gz'
        pattern = '''prefix_.*_[0-9]+\.blah\.
                     (?P<year>[0-9]{4})
                     (?P<month>[0-1][0-9])
                     (?P<day>[0-3][0-9])
                     (?P<hour>[0-2][0-9])00-[0-9]{2}00
                     -[0-9]?[0-9]\.gz'''
        files_that_should_match = []
        # add some files that match
        for i in range(24):
            fname = template % {
                'random': get_random_length_str(),
                'digits': get_random_length_str(16, string.digits),
                'datestr': datetime.now().strftime('%Y%m%d'),
                'hour': i,
                'next_hour': i + 1,
                'number': random.randint(0, 20),
            }
            files_that_should_match.append(fname)

        # add some files that don't match
        files = list(files_that_should_match)
        for i in range(24):
            fname = template % {
                'random': get_random_length_str(),
                'digits': get_random_length_str(16, string.digits),
                'datestr': datetime.now().strftime('%Y%m'),
                'hour': i,
                'next_hour': i + 1,
                'number': random.randint(0, 20),
            }
            files.append(fname)

        for fname in files:
            print(fname)

        with temptree(files, contents=[COMPRESSED_DATA] * len(files)) as t:
            self.assertEqual(len(os.listdir(t)), 48)
            conf = {'source_filename_pattern': pattern,
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'log_dir': t}
            uploader = MockLogUploader(conf)
            uploader.run_once()
            self.assertEqual(len(os.listdir(t)), 24)
            self.assertEqual(len(uploader.uploaded_files), 24)
            files_that_were_uploaded = set(x[0] for x in
                                           uploader.uploaded_files)
            for f in files_that_should_match:
                self.assertTrue(
                    os.path.join(t, f) in files_that_were_uploaded)

    def test_log_cutoff(self):
        files = [datetime.now().strftime('%Y%m%d%H')]
        with temptree(files) as t:
            conf = {'log_dir': t, 'new_log_cutoff': '7200',
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': access_regex}
            uploader = MockLogUploader(conf)
            uploader.run_once()
            self.assertEqual(len(uploader.uploaded_files), 0)
            conf = {'log_dir': t, 'new_log_cutoff': '0',
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': access_regex}
            uploader = MockLogUploader(conf)
            uploader.run_once()
            self.assertEqual(len(uploader.uploaded_files), 1)

    def test_create_container_fail(self):
        files = [datetime.now().strftime('%Y%m%d%H')]
        conf = {'source_filename_pattern': access_regex,
                'proxy_server_conf': PROXY_SERVER_CONF}
        with temptree(files) as t:
            conf['log_dir'] = t
            uploader = MockLogUploader(conf)
            uploader.run_once()
            self.assertEqual(len(uploader.uploaded_files), 1)

        with temptree(files) as t:
            conf['log_dir'] = t
            uploader = MockLogUploader(conf)
            # mock create_container to fail
            uploader.internal_proxy.create_container = lambda *args: False
            uploader.run_once()
            self.assertEqual(len(uploader.uploaded_files), 0)

    def test_unlink_log(self):
        files = [datetime.now().strftime('%Y%m%d%H')]
        with temptree(files, contents=[COMPRESSED_DATA]) as t:
            conf = {'log_dir': t, 'unlink_log': 'false',
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': access_regex}
            uploader = MockLogUploader(conf)
            uploader.run_once()
            self.assertEqual(len(uploader.uploaded_files), 1)
            # file still there
            self.assertEqual(len(os.listdir(t)), 1)

            conf = {'log_dir': t, 'unlink_log': 'true',
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': access_regex}
            uploader = MockLogUploader(conf)
            uploader.run_once()
            self.assertEqual(len(uploader.uploaded_files), 1)
            # file gone
            self.assertEqual(len(os.listdir(t)), 0)

    def test_upload_file_failed(self):
        files = ['plugin-%s' % datetime.now().strftime('%Y%m%d%H')]
        with temptree(files, contents=[COMPRESSED_DATA]) as t:
            conf = {'log_dir': t, 'unlink_log': 'true',
                    'proxy_server_conf': PROXY_SERVER_CONF,
                    'source_filename_pattern': access_regex}
            uploader = MockLogUploader(conf)

            # mock upload_file to fail, and clean up mock
            def mock_upload_file(self, *args, **kwargs):
                uploader.uploaded_files.pop()
                return False
            uploader.internal_proxy.upload_file = mock_upload_file
            self.assertRaises(SystemExit, uploader.run_once)
            # file still there
            self.assertEqual(len(os.listdir(t)), 1)


if __name__ == '__main__':
    unittest.main()
