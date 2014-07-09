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
#   This nagios plugin launches one or more tempest tests, collects results
#   and sets the result state accordingly.
#
# Example usage:
#   ./check_tempest.py -l /usr/share/python-tempest -r 'test.api.image.v2.*'
#

import argparse
import nose
import sys
import traceback

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3

def collect_args():
  """
  Collects args passed in the cli.
  """
  parser = argparse.ArgumentParser(
          description='Executes tempest tests and collects results')
  parser.add_argument('-l', '--location', dest='location', type=str, action='store',
      required=True, help='Location of the tests to be run')
  parser.add_argument('-r', '--regexp', dest='regexp', type=str, action='store',
      required=True, help='Do not verify certificates')
  parser.add_argument('-w','--failiswarn', dest='failiswarn', action='store_true',
      help='return warn on failure (default is critical)')
  return parser

def check_tempest(args):
  success = nose.run(argv=[
    'nosetests', "-w%s" % args.location, "-m%s" % args.regexp,
  ])

  if success:
    return STATE_OK

  if args.failiswarn:
    return STATE_WARNING
  else:
    return STATE_CRITICAL

if __name__ == '__main__':
  args = collect_args().parse_args()
  try:
    check_tempest(args)
  except Exception as e:
    traceback.print_exc()
    sys.exit(STATE_CRITICAL)
