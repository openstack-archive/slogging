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


from slogging import access_processor
import unittest


class TestAccessProcessor(unittest.TestCase):

    def test_CIDR_works(self):
        if access_processor.CIDR_support:
            p = access_processor.AccessLogProcessor({
                'lb_private_ips': '127.0.0.1,192.168/16,10/24'})
            self.assertTrue('192.168.2.3' in p.lb_private_ips)
            self.assertTrue('127.0.0.1' in p.lb_private_ips)
            self.assertFalse('192.167.2.3' in p.lb_private_ips)
        else:
            from nose import SkipTest
            raise SkipTest("iptools for CIDR support not installed")

    def test_CIDR_process_logs_with_missing_ip(self):
        if access_processor.CIDR_support:
            p = access_processor.AccessLogProcessor({
                'lb_private_ips': '127.0.0.1,192.168/16,10/24',
                'server_name': 'testsrv'})
            line = 'Sep 16 20:00:02 srv testsrv 199.115.119.21 - ' \
                   '16/Sep/2012/20/00/02 GET /v1/a/c/o HTTP/1.0 '  \
                   '200 - StaticWeb - - 17005 - txn - 0.0095 -'
            stream = [line]
            res = p.process(stream, 'dao', 'dac', 'don')
            self.assertEqual(res.keys()[0][0], 'a')
        else:
            from nose import SkipTest
            raise SkipTest("iptools for CIDR support not installed")

    def test_log_line_parser_query_args(self):
        p = access_processor.AccessLogProcessor({})
        log_line = [str(x) for x in range(18)]
        log_line[1] = 'proxy-server'
        log_line[4] = '1/Jan/3/4/5/6'
        query = 'foo'
        for param in access_processor.LISTING_PARAMS:
            query += '&%s=blah' % param
        log_line[6] = '/v1/a/c/o?%s' % query
        log_line = 'x' * 16 + ' '.join(log_line)
        res = p.log_line_parser(log_line)
        expected = {'code': 8, 'processing_time': '17', 'auth_token': '11',
                    'month': '01', 'second': '6', 'year': '3', 'tz': '+0000',
                    'http_version': '7', 'object_name': 'o', 'etag': '14',
                    'method': '5', 'trans_id': '15', 'client_ip': '2',
                    'bytes_out': 13, 'container_name': 'c', 'day': '1',
                    'minute': '5', 'account': 'a', 'hour': '4',
                    'referrer': '9', 'request': '/v1/a/c/o',
                    'user_agent': '10', 'bytes_in': 12, 'lb_ip': '3',
                    'log_source': None}
        for param in access_processor.LISTING_PARAMS:
            expected[param] = 1
        expected['query'] = query
        self.assertEqual(res, expected)

    def test_log_line_parser_query_args_with_slash_delimiter_to_container(
            self):
        p = access_processor.AccessLogProcessor({})
        log_line = [str(x) for x in range(18)]
        log_line[1] = 'proxy-server'
        log_line[4] = '1/Jan/3/4/5/6'
        query = 'prefix=YYYY/MM/DD'
        log_line[6] = '/v1/a/c?%s' % query
        log_line = 'x' * 16 + ' '.join(log_line)
        res = p.log_line_parser(log_line)

        self.assertEqual(res['object_name'], None)
        self.assertEqual(res['container_name'], 'c')
        self.assertEqual(res['account'], 'a')
        self.assertEqual(res['request'], '/v1/a/c')
        self.assertEqual(res['query'], query)

    def test_log_line_parser_query_args_with_slash_delimiter_to_account(self):
        p = access_processor.AccessLogProcessor({})
        log_line = [str(x) for x in range(18)]
        log_line[1] = 'proxy-server'
        log_line[4] = '1/Jan/3/4/5/6'
        query = 'prefix=YYYY/MM/DD'
        log_line[6] = '/v1/a?%s' % query
        log_line = 'x' * 16 + ' '.join(log_line)
        res = p.log_line_parser(log_line)

        self.assertEqual(res['object_name'], None)
        self.assertEqual(res['container_name'], None)
        self.assertEqual(res['account'], 'a')
        self.assertEqual(res['request'], '/v1/a')
        self.assertEqual(res['query'], query)

    def test_log_line_parser_field_count(self):
        p = access_processor.AccessLogProcessor({})
        # too few fields
        log_line = [str(x) for x in range(17)]
        log_line[1] = 'proxy-server'
        log_line[4] = '1/Jan/3/4/5/6'
        log_line[6] = '/v1/a/c/o'
        log_line = 'x' * 16 + ' '.join(log_line)
        res = p.log_line_parser(log_line)
        expected = {}
        self.assertEqual(res, expected)
        # right amount of fields
        log_line = [str(x) for x in range(18)]
        log_line[1] = 'proxy-server'
        log_line[4] = '1/Jan/3/4/5/6'
        log_line[6] = '/v1/a/c/o'
        log_line = 'x' * 16 + ' '.join(log_line)
        res = p.log_line_parser(log_line)
        expected = {'code': 8, 'processing_time': '17', 'auth_token': '11',
                    'month': '01', 'second': '6', 'year': '3', 'tz': '+0000',
                    'http_version': '7', 'object_name': 'o', 'etag': '14',
                    'method': '5', 'trans_id': '15', 'client_ip': '2',
                    'bytes_out': 13, 'container_name': 'c', 'day': '1',
                    'minute': '5', 'account': 'a', 'hour': '4',
                    'referrer': '9', 'request': '/v1/a/c/o',
                    'user_agent': '10', 'bytes_in': 12, 'lb_ip': '3',
                    'log_source': None}
        self.assertEqual(res, expected)
        # too many fields
        log_line = [str(x) for x in range(19)]
        log_line[1] = 'proxy-server'
        log_line[4] = '1/Jan/3/4/5/6'
        log_line[6] = '/v1/a/c/o'
        log_line = 'x' * 16 + ' '.join(log_line)
        res = p.log_line_parser(log_line)
        expected = {'code': 8, 'processing_time': '17', 'auth_token': '11',
                    'month': '01', 'second': '6', 'year': '3', 'tz': '+0000',
                    'http_version': '7', 'object_name': 'o', 'etag': '14',
                    'method': '5', 'trans_id': '15', 'client_ip': '2',
                    'bytes_out': 13, 'container_name': 'c', 'day': '1',
                    'minute': '5', 'account': 'a', 'hour': '4',
                    'referrer': '9', 'request': '/v1/a/c/o',
                    'user_agent': '10', 'bytes_in': 12, 'lb_ip': '3',
                    'log_source': '18'}
        self.assertEqual(res, expected)


if __name__ == '__main__':
    unittest.main()
