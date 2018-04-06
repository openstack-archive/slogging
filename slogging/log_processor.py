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
import cPickle
import cStringIO
import datetime
import hashlib
import io
import json
from slogging import common
from slogging import log_common
from swift.common.daemon import Daemon
from swift.common import utils
import time
from tzlocal import get_localzone


now = datetime.datetime.now
local_zone = get_localzone()


class LogProcessor(log_common.LogProcessorCommon):
    """LogProcessor class.

    Load plugins, process logs
    """
    def __init__(self, conf, logger):
        basic_conf = conf['log-processor']
        super(LogProcessor, self).__init__(basic_conf, logger, 'log-processor')

        # load the processing plugins
        self.plugins = {}
        plugin_prefix = 'log-processor-'
        for section in (x for x in conf if x.startswith(plugin_prefix)):
            plugin_name = section[len(plugin_prefix):]
            plugin_conf = conf.get(section, {})
            self.plugins[plugin_name] = plugin_conf
            class_path = self.plugins[plugin_name]['class_path']
            import_target, class_name = class_path.rsplit('.', 1)
            module = __import__(import_target, fromlist=[import_target])
            klass = getattr(module, class_name)
            self.plugins[plugin_name]['instance'] = klass(plugin_conf)
            self.plugins[plugin_name]['keylist_mapping'] = {}
            self.logger.debug(_('Loaded plugin "%s"') % plugin_name)

    def process_one_file(self, plugin_name, account, container, object_name):
        self.logger.info(_('Processing %(obj)s with plugin "%(plugin)s"') %
                         {'obj': '/'.join((account, container, object_name)),
                          'plugin': plugin_name})
        # get an iter of the object data
        compressed = object_name.endswith('.gz')
        stream = self.get_object_data(account, container, object_name,
                                      compressed=compressed)
        # look up the correct plugin and send the stream to it
        return self.plugins[plugin_name]['instance'].process(stream,
                                                             account,
                                                             container,
                                                             object_name)

    def get_data_list(self, start_date=None, end_date=None,
                      listing_filter=None):
        total_list = []
        for plugin_name, data in self.plugins.items():
            account = data['swift_account']
            container = data['container_name']
            listing = self.get_container_listing(account,
                                                 container,
                                                 start_date,
                                                 end_date)
            for object_name in listing:
                # The items in this list end up being passed as positional
                # parameters to process_one_file.
                x = (plugin_name, account, container, object_name)
                if x not in listing_filter:
                    total_list.append(x)
        return total_list

    def generate_keylist_mapping(self):
        keylist = {}
        for plugin in self.plugins:
            plugin_keylist = self.plugins[plugin]['keylist_mapping'] = \
                self.plugins[plugin]['instance'].keylist_mapping()
            if not plugin_keylist:
                continue
            for k, v in plugin_keylist.items():
                o = keylist.get(k)
                if o:
                    if isinstance(o, set):
                        if isinstance(v, set):
                            o.update(v)
                        else:
                            o.update([v])
                    else:
                        o = set(o)
                        if isinstance(v, set):
                            o.update(v)
                        else:
                            o.update([v])
                else:
                    o = v
                keylist[k] = o
        return keylist


class LogProcessorDaemon(Daemon):
    """Log Processor Daemon class.

    Gather raw log data and farm processing to generate a csv that is
    uploaded to swift.
    """
    def __init__(self, conf):
        c = conf.get('log-processor')
        super(LogProcessorDaemon, self).__init__(c)
        self.total_conf = conf
        self.logger = utils.get_logger(c, log_route='log-processor')
        self.log_processor = LogProcessor(conf, self.logger)
        self.lookback_hours = int(c.get('lookback_hours', '120'))
        self.lookback_window = int(c.get('lookback_window',
                                   str(self.lookback_hours)))
        self.log_processor_account = c['swift_account']
        self.log_processor_container = c.get('container_name',
                                             'log_processing_data')
        self.worker_count = int(c.get('worker_count', '1'))
        self._keylist_mapping = None
        self.processed_files_filename = 'processed_files.pickle.gz'
        self.time_zone = common.get_time_zone(c, self.logger, 'time_zone',
                                              str(local_zone))
        self.format_type = common.get_format_type(c, self.logger,
                                                  'format_type', 'csv')

    def get_lookback_interval(self):
        """Get lookback interval.

        :returns: lookback_start, lookback_end.

            Both or just lookback_end can be None. Otherwise, returns strings
            of the form 'YYYYMMDDHH'. The interval returned is used as bounds
            when looking for logs to processes.

            A returned None means don't limit the log files examined on that
            side of the interval.
        """

        if self.lookback_hours == 0:
            lookback_start = None
            lookback_end = None
        else:
            delta_hours = datetime.timedelta(hours=self.lookback_hours)
            lookback_start = now(self.time_zone) - delta_hours
            lookback_start = lookback_start.strftime('%Y%m%d%H')
            if self.lookback_window == 0:
                lookback_end = None
            else:
                delta_window = datetime.timedelta(hours=self.lookback_window)
                lookback_end = now(self.time_zone) - delta_hours + delta_window
                lookback_end = lookback_end.strftime('%Y%m%d%H')
        return lookback_start, lookback_end

    def get_processed_files_list(self):
        """Downloads the set from the stats account.

        Creates an empty set if the an existing file cannot be found.

        :returns: a set of files that have already been processed or returns
            None on error.
        """
        try:
            # Note: this file (or data set) will grow without bound.
            # In practice, if it becomes a problem (say, after many months of
            # running), one could manually prune the file to remove older
            # entries. Automatically pruning on each run could be dangerous.
            # There is not a good way to determine when an old entry should be
            # pruned (lookback_hours could be set to anything and could change)
            stream = self.log_processor.get_object_data(
                self.log_processor_account,
                self.log_processor_container,
                self.processed_files_filename,
                compressed=True)
            buf = '\n'.join(x for x in stream)
            if buf:
                files = cPickle.loads(buf)
            else:
                return None
        except log_common.BadFileDownload as err:
            if err.status_code == 404:
                files = set()
            else:
                return None
        return files

    def get_aggregate_data(self, processed_files, input_data):
        """Aggregates stats data by account/hour, summing as needed.

        :param processed_files: set of processed files
        :param input_data: is the output from
            log_common.multiprocess_collate/the plugins.

        :returns: A dict containing data aggregated from the input_data
        passed in.

            The dict returned has tuple keys of the form:
                (account, year, month, day, hour)
            The dict returned has values that are dicts with items of this
                form:
            key:field_value
                - key corresponds to something in one of the plugin's keylist
                mapping, something like the tuple (source, level, verb, code)
                - field_value is the sum of the field_values for the
                corresponding values in the input

            Both input_data and the dict returned are hourly aggregations of
            stats.

            Multiple values for the same (account, hour, tuple key) found in
            input_data are summed in the dict returned.
        """

        aggr_data = {}
        for item, data in input_data:
            # since item contains the plugin and the log name, new plugins will
            # "reprocess" the file and the results will be in the final csv.
            processed_files.add(item)
            for k, d in data.items():
                existing_data = aggr_data.get(k, {})
                for i, j in d.items():
                    current = existing_data.get(i, 0)
                    # merging strategy for key collisions is addition
                    # processing plugins need to realize this
                    existing_data[i] = current + j
                aggr_data[k] = existing_data
        return aggr_data

    def get_final_info(self, aggr_data):
        """Aggregates data from aggr_data based on the keylist mapping.

        :param aggr_data: The results of the get_aggregate_data function.
        :returns: a dict of further aggregated data

            The dict returned has keys of the form:
                (account, year, month, day, hour)
            The dict returned has values that are dicts with items of this
                 form:
                'field_name': field_value (int)

            Data is aggregated as specified by the keylist mapping. The
            keylist mapping specifies which keys to combine in aggr_data
            and the final field_names for these combined keys in the dict
            returned. Fields combined are summed.
        """

        final_info = collections.defaultdict(dict)
        for account, data in aggr_data.items():
            for key, mapping in self.keylist_mapping.items():
                if isinstance(mapping, (list, set)):
                    value = 0
                    for k in mapping:
                        try:
                            value += data[k]
                        except KeyError:
                            pass
                else:
                    try:
                        value = data[mapping]
                    except KeyError:
                        value = 0
                final_info[account][key] = value
        return final_info

    def store_processed_files_list(self, processed_files):
        """Stores the proccessed files list in the stats account.

        :param processed_files: set of processed files
        """

        s = cPickle.dumps(processed_files, cPickle.HIGHEST_PROTOCOL)
        f = cStringIO.StringIO(s)
        self.log_processor.internal_proxy.upload_file(
            f,
            self.log_processor_account,
            self.log_processor_container,
            self.processed_files_filename)

    def get_output(self, final_info):
        """Return data according to given format_type.

        :returns: a list of rows to appear in the csv file or
                  a dictionary to appear in the json file.

            csv file:
                The first row contains the column headers for the rest
                of the rows in the returned list.

                Each row after the first row corresponds to an account's
                data.
            json file:
                First level just shows a label "stats_data".
                Second level of stats_data lists account names.
                Each account block starts with a time label, and it
                contains stats of account usage.
        """

        if self.format_type == 'json':
            all_account_stats = collections.defaultdict(dict)
            for (account, year, month, day, hour), d in final_info.items():
                data_ts = datetime.datetime(int(year), int(month),
                                            int(day), int(hour),
                                            tzinfo=self.time_zone)
                time_stamp = data_ts.strftime('%Y/%m/%d %H:00:00 %z')
                hourly_account_stats = \
                    self.restructure_stats_dictionary(d)
                all_account_stats[account].update({time_stamp:
                                                   hourly_account_stats})
            output = {'time_zone': str(self.time_zone),
                      'stats_data': all_account_stats}
        else:  # csv
            sorted_keylist_mapping = sorted(self.keylist_mapping)
            columns = ['data_ts', 'account'] + sorted_keylist_mapping
            output = [columns]
            for (account, year, month, day, hour), d in final_info.items():
                data_ts = '%04d/%02d/%02d %02d:00:00' % \
                    (int(year), int(month), int(day), int(hour))
                row = [data_ts, '%s' % (account)]
                for k in sorted_keylist_mapping:
                    row.append(str(d[k]))
                output.append(row)
        return output

    def restructure_stats_dictionary(self, target_dict):
        """Restructure stats dictionary for json format.

        :param target_dict: dictionary of restructuring target
        :returns: restructured stats dictionary
        """
        account_stats = {}
        access_stats = {}
        account_stats_key_list = \
            self.log_processor.plugins['stats']['keylist_mapping']
        access_stats_key_list = \
            self.log_processor.plugins['access']['keylist_mapping']
        hourly_stats = {'account_stats': account_stats,
                        'access_stats': access_stats}
        for k, v in target_dict.items():
            if k in account_stats_key_list:
                account_stats[k] = int(v)
            elif k in access_stats_key_list:
                access_stats[k] = int(v)
        return hourly_stats

    def store_output(self, output):
        """Takes the dictionary or the list of rows.

        And stores a json/csv file of the values in the stats account.

        :param output: a dictionary or a list of row
            This json or csv file is final product of this script.
        """
        if self.format_type == 'json':
            out_buf = json.dumps(output, indent=2)
            h = hashlib.md5(out_buf).hexdigest()
            upload_name = datetime.datetime.now(self.time_zone).strftime(
                '%Y/%m/%d/%H/') + '%s.json.gz' % h
            f = io.BytesIO(out_buf)
        else:
            out_buf = '\n'.join([','.join(row) for row in output])
            h = hashlib.md5(out_buf).hexdigest()
            upload_name = datetime.datetime.now(self.time_zone).strftime(
                '%Y/%m/%d/%H/') + '%s.csv.gz' % h
            f = cStringIO.StringIO(out_buf)
        self.log_processor.internal_proxy.upload_file(
            f,
            self.log_processor_account,
            self.log_processor_container,
            upload_name)

    @property
    def keylist_mapping(self):
        """Determines how the stats fields are aggregated in the fila step."""
        if self._keylist_mapping is None:
            self._keylist_mapping = \
                self.log_processor.generate_keylist_mapping()
        return self._keylist_mapping

    def process_logs(self, logs_to_process, processed_files):
        """Process logs and returns result as list.

        :param logs_to_process: list of logs to process
        :param processed_files: set of processed files

        :returns: returns a list of rows of processed data.
            The first row is the column headers. The rest of the rows contain
            hourly aggregate data for the account specified in the row.

            Files processed are added to the processed_files set.

            When a large data structure is no longer needed, it is deleted in
            an effort to conserve memory.
        """

        # map
        processor_args = (self.total_conf, self.logger)
        results = log_common.multiprocess_collate(
            LogProcessor,
            processor_args,
            'process_one_file',
            logs_to_process,
            self.worker_count)

        # reduce
        aggr_data = self.get_aggregate_data(processed_files, results)
        del results

        # group
        # reduce a large number of keys in aggr_data[k] to a small
        # number of output keys
        final_info = self.get_final_info(aggr_data)
        del aggr_data

        # output
        return self.get_output(final_info)

    def run_once(self, *args, **kwargs):
        """Process log files that fall within the lookback interval.

        Upload resulting csv or json file to stats account.
        Update processed files list and upload to stats account.
        """
        for k in 'lookback_hours lookback_window'.split():
            if k in kwargs and kwargs[k] is not None:
                setattr(self, k, kwargs[k])

        start = time.time()
        self.logger.info(_("Beginning log processing"))

        lookback_start, lookback_end = self.get_lookback_interval()
        self.logger.debug('lookback_start: %s' % lookback_start)
        self.logger.debug('lookback_end: %s' % lookback_end)

        processed_files = self.get_processed_files_list()
        if processed_files is None:
            self.logger.error(_('Log processing unable to load list of '
                                'already processed log files'))
            return
        self.logger.debug(_('found %d processed files') %
                          len(processed_files))

        logs_to_process = self.log_processor.get_data_list(
            lookback_start,
            lookback_end, processed_files)
        self.logger.info(_('loaded %d files to process') %
                         len(logs_to_process))

        if logs_to_process:
            output = self.process_logs(logs_to_process, processed_files)
            self.store_output(output)
            del output

            self.store_processed_files_list(processed_files)

        self.logger.info(_("Log processing done (%0.2f minutes)") %
                         ((time.time() - start) / 60))
