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


from contextlib import contextmanager
import copy
from eventlet.green import socket
import logging
import logging.handlers
import os
from shutil import rmtree
from swift.common.utils import readconf
from swift.common.utils import TRUE_VALUES
import sys
from sys import exc_info
from tempfile import mkdtemp
from tempfile import NamedTemporaryFile


def get_config(section_name=None, defaults=None):
    """Attempt to get a test config dictionary.

    :param section_name: the section to read (all sections if not defined)
    :param defaults: an optional dictionary namespace of defaults
    """
    config_file = os.environ.get('SWIFT_TEST_CONFIG_FILE',
                                 '/etc/swift/test.conf')
    config = {}
    if defaults is not None:
        config.update(defaults)

    try:
        config = readconf(config_file, section_name)
    except SystemExit:
        if not os.path.exists(config_file):
            msg = 'Unable to read test config ' \
                  '%s - file not found\n' % config_file
        elif not os.access(config_file, os.R_OK):
            msg = 'Unable to read test config %s - ' \
                  'permission denied' % config_file
        else:
            values = {'config_file': config_file,
                      'section_name': section_name}
            msg = 'Unable to read test config %(config_file)s - ' \
                  'section %(section_name)s not found' % values
        sys.stderr.write(msg)
    return config


def readuntil2crlfs(fd):
    rv = ''
    lc = ''
    crlfs = 0
    while crlfs < 2:
        c = fd.read(1)
        rv = rv + c
        if c == '\r' and lc != '\n':
            crlfs = 0
        if lc == '\r' and c == '\n':
            crlfs += 1
        lc = c
    return rv


def connect_tcp(hostport):
    rv = socket.socket()
    rv.connect(hostport)
    return rv


@contextmanager
def tmpfile(content):
    with NamedTemporaryFile('w', delete=False) as f:
        file_name = f.name
        f.write(str(content))
    try:
        yield file_name
    finally:
        os.unlink(file_name)

xattr_data = {}


def _get_inode(fd):
    if not isinstance(fd, int):
        try:
            fd = fd.fileno()
        except AttributeError:
            return os.stat(fd).st_ino
    return os.fstat(fd).st_ino


def _setxattr(fd, k, v):
    inode = _get_inode(fd)
    data = xattr_data.get(inode, {})
    data[k] = v
    xattr_data[inode] = data


def _getxattr(fd, k):
    inode = _get_inode(fd)
    data = xattr_data.get(inode, {}).get(k)
    if not data:
        raise IOError
    return data

import xattr
xattr.setxattr = _setxattr
xattr.getxattr = _getxattr


@contextmanager
def temptree(files, contents=''):
    # generate enough contents to fill the files
    c = len(files)
    contents = (list(contents) + [''] * c)[:c]
    tempdir = mkdtemp()
    for path, content in zip(files, contents):
        if os.path.isabs(path):
            path = '.' + path
        new_path = os.path.join(tempdir, path)
        subdir = os.path.dirname(new_path)
        if not os.path.exists(subdir):
            os.makedirs(subdir)
        with open(new_path, 'w') as f:
            f.write(str(content))
    try:
        yield tempdir
    finally:
        rmtree(tempdir)


class NullLoggingHandler(logging.Handler):

    def emit(self, record):
        pass


class FakeLogger(object):
    # a thread safe logger

    def __init__(self, *args, **kwargs):
        self._clear()
        self.level = logging.NOTSET
        if 'facility' in kwargs:
            self.facility = kwargs['facility']

    def _clear(self):
        self.log_dict = dict(
            error=[], info=[], warning=[], debug=[], exception=[])

    def error(self, *args, **kwargs):
        self.log_dict['error'].append((args, kwargs))

    def info(self, *args, **kwargs):
        self.log_dict['info'].append((args, kwargs))

    def warning(self, *args, **kwargs):
        self.log_dict['warning'].append((args, kwargs))

    def debug(self, *args, **kwargs):
        self.log_dict['debug'].append((args, kwargs))

    def exception(self, *args, **kwargs):
        self.log_dict['exception'].append((args, kwargs, str(exc_info()[1])))

    # mock out the StatsD logging methods:
    def set_statsd_prefix(self, *a, **kw):
        pass

    increment = decrement = timing = \
        timing_since = update_stats = set_statsd_prefix

    def setFormatter(self, obj):
        self.formatter = obj

    def close(self):
        self._clear()

    def set_name(self, name):
        # don't touch _handlers
        self._name = name

    def acquire(self):
        pass

    def release(self):
        pass

    def createLock(self):
        pass

    def emit(self, record):
        pass

    def handle(self, record):
        pass

    def flush(self):
        pass

    def handleError(self, record):
        pass


original_syslog_handler = logging.handlers.SysLogHandler


def fake_syslog_handler():
    for attr in dir(original_syslog_handler):
        if attr.startswith('LOG'):
            setattr(FakeLogger, attr,
                    copy.copy(getattr(logging.handlers.SysLogHandler, attr)))
    FakeLogger.priority_map = \
        copy.deepcopy(logging.handlers.SysLogHandler.priority_map)

    logging.handlers.SysLogHandler = FakeLogger


if get_config('unit_test').get('fake_syslog', 'False').lower() in TRUE_VALUES:
    fake_syslog_handler()


class MockTrue(object):
    """Instances of MockTrue evaluate like True

    Any attr accessed on an instance of MockTrue will return a MockTrue
    instance. Any method called on an instance of MockTrue will return
    a MockTrue instance.

    >>> thing = MockTrue()
    >>> thing
    True
    >>> thing == True # True == True
    True
    >>> thing == False # True == False
    False
    >>> thing != True # True != True
    False
    >>> thing != False # True != False
    True
    >>> thing.attribute
    True
    >>> thing.method()
    True
    >>> thing.attribute.method()
    True
    >>> thing.method().attribute
    True
    """
    def __getattribute__(self, *args, **kwargs):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def __repr__(*args, **kwargs):
        return repr(True)

    def __eq__(self, other):
        return other is True

    def __ne__(self, other):
        return other is not True
