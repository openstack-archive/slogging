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


import datetime
import iptools
import unittest


class TestAccessProcessorSpeed(unittest.TestCase):

    def test_CIDR_speed(self):
        line = 'Sep 16 20:00:02 srv testsrv 192.%s.119.%s - ' \
               '16/Sep/2012/20/00/02 GET /v1/a/c/o HTTP/1.0 ' \
               '200 - StaticWeb - - 17005 - txn - 0.0095 -'
        ips1 = iptools.IpRangeList(*[x.strip() for x in
                                     '127.0.0.1,192.168/16,10/24'.split(',')
                                     if x.strip()])
        ips2 = iptools.IpRangeList(*[x.strip() for x in
                                     '172.168/16,10/30'.split(',')
                                     if x.strip()])
        ips3 = iptools.IpRangeList(*[x.strip() for x in
                                     '127.0.0.1,11/24'.split(',')
                                     if x.strip()])

        orig_start = datetime.datetime.utcnow()
        hit = 0
        for n in range(255):
            for a in range(255):
                stream = line % (n, a)
                data = stream.split(" ")
                if data[5] in ips1 or data[5] in ips2 or data[5] in ips3:
                    hit += 1
        orig_end = datetime.datetime.utcnow()
        orig_secs = float("%d.%d" % ((orig_end - orig_start).seconds,
                          (orig_end - orig_start).microseconds))
        self.assertEqual(hit, 255)

        # now, let's check the speed with sets
        set1 = set(k for k in ips1)
        set2 = set(k for k in ips2)
        set3 = set(k for k in ips3)

        new_start = datetime.datetime.utcnow()
        hit = 0
        for n in range(255):
            for a in range(255):
                stream = line % (n, a)
                data = stream.split(" ")
                if data[5] in set1 or data[5] in set2 or data[5] in set3:
                    hit += 1
        new_end = datetime.datetime.utcnow()
        new_secs = float("%d.%d" % ((new_end - new_start).seconds,
                         (new_end - new_start).microseconds))
        self.assertEqual(hit, 255)

        # assert that using pure types directly is faster
        self.assertTrue(new_secs < orig_secs)


if __name__ == '__main__':
    unittest.main()
