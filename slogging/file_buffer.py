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

import collections
import errno
import os
from swift.common.exceptions import LockTimeout
from swift.common.utils import lock_file


class FileBuffer(object):
    """FileBuffer class"""

    def __init__(self, limit, logger):
        self.buffers = collections.defaultdict(list)
        self.limit = limit
        self.logger = logger
        self.total_size = 0

    def write(self, filename, data):
        self.buffers[filename].append(data)
        self.total_size += len(data)
        if self.total_size >= self.limit:
            self.flush()

    def flush(self):
        while self.buffers:
            filename_list = self.buffers.keys()
            for filename in filename_list:
                out = '\n'.join(self.buffers[filename]) + '\n'
                mid_dirs = os.path.dirname(filename)
                try:
                    os.makedirs(mid_dirs)
                except OSError as err:
                    if err.errno == errno.EEXIST:
                        pass
                    else:
                        raise
                try:
                    with lock_file(filename, append=True, unlink=False) as f:
                        f.write(out)
                except LockTimeout:
                    # couldn't write, we'll try again later
                    self.logger.debug(_('Timeout writing to %s') % filename)
                else:
                    del self.buffers[filename]
        self.total_size = 0
