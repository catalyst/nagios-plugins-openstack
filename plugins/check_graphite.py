#!/usr/bin/env python
#
# vim: tabstop=2 shiftwidth=2
#
# Copyright (C) 2014 Catalyst IT Limited.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; only version 2 of the License is applicable.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# Authors:
#   Ricardo Rocha <ricardo@catalyst.net.nz>
#
# About this plugin:
#   This nagios plugin executes a graphite query, checking that results are
#   retrieved. Useful to make sure expected data is being published.
#
#   Check: http://graphite.readthedocs.org/en/1.0/url-api.html
#   for more information on the 'target' and 'from' options.
#
# Example usage:
#   ./check_graphite.py -H icinga.example.com -P 80 -p http -t 'collectd.*.ceph-ceph.cluster.gauge.total_avail' -f '-10minutes'
#

import argparse
import json
import sys
import traceback
import urllib2

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3

def collect_args():
  """
  Collects args passed in the cli.
  """
  parser = argparse.ArgumentParser(
    description='Executes a graphite query and checks for results')
  parser.add_argument('-H', '--host', dest='host', type=str, action='store',
    required=True, help='Graphite host to contact')
  parser.add_argument('-P', '--port', dest='port', type=str, action='store',
    default='80', help='Port the graphite daemon listens')
  parser.add_argument('-p', '--proto', dest='proto', type=str, action='store',
    default='http', help='Protocol to use (one of http/https)')
  parser.add_argument('-s', '--subpath', dest='subpath', type=str, action='store',
    default='', help='Subpath of graphite the host url')
  parser.add_argument('-t', '--target', dest='target', type=str, action='store',
    required=True, help='Target query (the metric to query for)')
  parser.add_argument('-f', '--from', dest='interval', type=str, action='store',
    required=True, help='Interval to query for (check \'from\' in graphite)')
  parser.add_argument('-w','--failiswarn', dest='failiswarn', action='store_true',
      help='Return warn on failure (default is critical)')
  parser.add_argument('-v','--verbose', dest='verbose', action='store_true',
      help='Print some additional information')
  return parser

def check_graphite(args):

  query = "%s://%s:%s/%srender/?target=%s&from=%s&format=json" % (
    args.proto, args.host, args.port, args.subpath, args.target, args.interval)

  result = urllib2.urlopen(query).read()
  if args.verbose:
    print result
  jsonres = json.loads(result)

  if len(jsonres) > 0 and len(jsonres[0]['datapoints']) > 0:
    print "OK: query %s retrieved %d elements" % (query, len(jsonres[0]['datapoints']))
    return STATE_OK

  print "Failed: query %s returned %s" % (query, result)

  if args.failiswarn:
    return STATE_WARNING
  else:
    return STATE_CRITICAL

if __name__ == '__main__':
  args = collect_args().parse_args()
  try:
    sys.exit(check_graphite(args))
  except Exception as e:
    print "Failed: %s" % str(e)
    sys.exit(STATE_CRITICAL)
