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

import json
from slogging import internal_proxy
from swift.common import swob
import tempfile
import unittest


class DumbApplicationFactory(object):

    def __init__(self, status_codes, body=''):
        self.status_codes = status_codes[:]
        self.body = body

    def __call__(self, *a, **kw):
        app = DumbApplication(*a, **kw)
        app.status_codes = self.status_codes
        try:
            app.default_status_code = self.status_codes[-1]
        except IndexError:
            app.default_status_code = 200
        app.body = self.body
        return app


class DumbApplication(object):

    def __init__(self, *a, **kw):
        self.status_codes = []
        self.default_status_code = 200
        self.call_count = 0
        self.body = ''

    def handle_request(self, req):
        self.call_count += 1
        req.path_info_pop()
        if isinstance(self.body, list):
            try:
                body = self.body.pop(0)
            except IndexError:
                body = ''
        else:
            body = self.body
        resp = swob.Response(request=req, body=body,
                             conditional_response=True)
        try:
            resp.status_int = self.status_codes.pop(0)
        except IndexError:
            resp.status_int = self.default_status_code
        resp.app_iter = iter(body)
        return resp

    def update_request(self, req):
        return req


class TestInternalProxy(unittest.TestCase):

    def test_swob_request_copy(self):
        req = swob.Request.blank('/')
        req2 = internal_proxy.swob_request_copy(req)
        self.assertEqual(req.path, req2.path)
        self.assertEqual(req.path_info, req2.path_info)
        self.assertFalse(req is req2)
        self.assertEqual(req.headers, req2.headers)
        self.assertFalse(req.headers is req2.headers)

    def test_handle_request(self):
        status_codes = [200]
        internal_proxy.Application = DumbApplicationFactory(status_codes)
        p = internal_proxy.InternalProxy()
        req = swob.Request.blank('/')
        orig_req = internal_proxy.swob_request_copy(req)
        p._handle_request(req)
        self.assertEqual(req.path_info, orig_req.path_info)

    def test_handle_request_with_retries(self):
        status_codes = [500, 200]
        internal_proxy.Application = DumbApplicationFactory(status_codes)
        p = internal_proxy.InternalProxy(retries=3)
        req = swob.Request.blank('/')
        orig_req = internal_proxy.swob_request_copy(req)
        resp = p._handle_request(req)
        self.assertEqual(req.path_info, orig_req.path_info)
        self.assertEqual(p.upload_app.call_count, 2)
        self.assertEqual(resp.status_int, 200)

    def test_get_object(self):
        status_codes = [200]
        internal_proxy.Application = DumbApplicationFactory(status_codes)
        p = internal_proxy.InternalProxy()
        code, body = p.get_object('a', 'c', 'o')
        body = ''.join(body)
        self.assertEqual(code, 200)
        self.assertEqual(body, '')

    def test_create_container(self):
        status_codes = [200]
        internal_proxy.Application = DumbApplicationFactory(status_codes)
        p = internal_proxy.InternalProxy()
        resp = p.create_container('a', 'c')
        self.assertTrue(resp)

    def test_handle_request_with_retries_all_error(self):
        status_codes = [500, 500, 500, 500, 500]
        internal_proxy.Application = DumbApplicationFactory(status_codes)
        p = internal_proxy.InternalProxy(retries=3)
        req = swob.Request.blank('/')
        orig_req = internal_proxy.swob_request_copy(req)
        resp = p._handle_request(req)
        self.assertEqual(req.path_info, orig_req.path_info)
        self.assertEqual(p.upload_app.call_count, 3)
        self.assertEqual(resp.status_int, 500)

    def test_get_container_list_empty(self):
        status_codes = [200]
        internal_proxy.Application = DumbApplicationFactory(status_codes,
                                                            body='[]')
        p = internal_proxy.InternalProxy()
        resp = p.get_container_list('a', 'c')
        self.assertEqual(resp, [])

    def test_get_container_list_no_body(self):
        status_codes = [204]
        internal_proxy.Application = DumbApplicationFactory(status_codes,
                                                            body='')
        p = internal_proxy.InternalProxy()
        resp = p.get_container_list('a', 'c')
        self.assertEqual(resp, [])

    def test_get_container_list_full_listing(self):
        status_codes = [200, 200]
        obj_a = dict(name='foo', hash='foo', bytes=3,
                     content_type='text/plain', last_modified='2011/01/01')
        obj_b = dict(name='bar', hash='bar', bytes=3,
                     content_type='text/plain', last_modified='2011/01/01')
        body = [json.dumps([obj_a]), json.dumps([obj_b]), json.dumps([])]
        internal_proxy.Application = DumbApplicationFactory(status_codes,
                                                            body=body)
        p = internal_proxy.InternalProxy()
        resp = p.get_container_list('a', 'c')
        expected = ['foo', 'bar']
        self.assertEqual([x['name'] for x in resp], expected)

    def test_get_container_list_full(self):
        status_codes = [204]
        internal_proxy.Application = DumbApplicationFactory(status_codes,
                                                            body='')
        p = internal_proxy.InternalProxy()
        resp = p.get_container_list('a', 'c', marker='a', end_marker='b',
                                    limit=100, prefix='/', delimiter='.')
        self.assertEqual(resp, [])

    def test_upload_file(self):
        status_codes = [200, 200]  # container PUT + object PUT
        internal_proxy.Application = DumbApplicationFactory(status_codes)
        p = internal_proxy.InternalProxy()
        with tempfile.NamedTemporaryFile() as file_obj:
            resp = p.upload_file(file_obj.name, 'a', 'c', 'o')
        self.assertTrue(resp)

    def test_upload_file_with_retries(self):
        status_codes = [200, 500, 200]  # container PUT + error + object PUT
        internal_proxy.Application = \
            DumbApplicationFactory(status_codes)
        p = internal_proxy.InternalProxy(retries=3)
        with tempfile.NamedTemporaryFile() as file_obj:
            resp = p.upload_file(file_obj, 'a', 'c', 'o')
        self.assertTrue(resp)
        self.assertEqual(p.upload_app.call_count, 3)


if __name__ == '__main__':
    unittest.main()
