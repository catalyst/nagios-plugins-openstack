#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Nagios event handler to evacuate VMs on a compute node failure.
#
# Copyright 2014 Catalyst IT.
#
# Author: Ricardo Rocha <ricardo@catalyst.net.nz>
#         Fei Long Wang <flwang@catalyst.net.nz>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import argparse
import sys
import syslog
from datetime import datetime
from datetime import timedelta
import time
from novaclient.v1_1 import client as nclient

syslog.openlog('nagios-nova-evacuate', 0, syslog.LOG_USER)


# State ID values for HOST states in nagios
UP = 0
DOWN = 1
UNREACHABLE = 2


# Argument parsing, as given by Nagios
parser = argparse.ArgumentParser(description='Evacuate VMs from compute node')
parser.add_argument('--auth_url', metavar='URL', type=str, required=True,
                    help='Endpoint to the keystone service')
parser.add_argument('--username', metavar='username', type=str, required=True,
                    help='username to use for authentication')
parser.add_argument('--password', metavar='password', type=str, required=True,
                    help='password to use for authentication')
parser.add_argument('--tenant', metavar='tenant', type=str, required=True,
                    help='tenant name to use for authentication')
parser.add_argument('--region_name', metavar='region_name', type=str,
                    required=True, help='Region to select for authentication')
parser.add_argument('--ca-cert', metavar='ca_cert', type=str,
                    help='Location of CA validation cert')
parser.add_argument('--insecure', action='store_true', default=False,
                    help='Do not perform certificate validation')
parser.add_argument('--unreachable-is-down', action='store_true',
                    default=False,
                    help='True if we trigger evacuate on node unreachable')
parser.add_argument('--wait-timeout', metavar='wait_timeout', default=10,
                    help='Time (in seconds) to wait for a successful '
                    'evacuation before reporting failure')
parser.add_argument('compute_host', metavar='compute_host', type=str,
                    help='Hostname of the compute node to evacuate')
parser.add_argument('state', metavar='state', type=str,
                    help='Current state of probe (UP, DOWN, UNREACHEABLE)')
parser.add_argument('state_type', metavar='state_type', type=str,
                    help='Current state type of probe (HARD, SOFT)')

args = parser.parse_args()

# By default unreachable does not trigger evacuate, but it's configurable
down_states = [DOWN]
if args.unreachable_is_down:
    down_states.append(UNREACHABLE)


# Is the state DOWN, and the state type HARD? Otherwise we do nothing for now.
if args.state_type != 'HARD' and args.state not in down_states:
    syslog.syslog("%s down, but probe not in HARD state yet (not running)" %
                  args.compute_host)
    sys.exit(0)

syslog.syslog("%s DOWN and probe in HARD state, evacuating VMs" %
              args.compute_host)

# Get a nova client object (it takes care of keystone auth too)
try:
    nova = nclient.Client(args.username, args.password, args.tenant,
                          auth_url=args.auth_url, insecure=args.insecure,
                          region_name=args.region_name)
except Exception as e:
    syslog.syslog(syslog.LOG_ERR, "Failed to authenticate to keystone: %s" %
                  str(e))
    sys.exit(-1)

# Check nova-compute is marked down for the compute host
for binary in ['nova-compute']:
    try:
        service_state = nova.services.list(host=args.compute_host,
                                           binary=binary)

        if len(service_state) != 1:
            syslog.syslog(syslog.LOG_ERR, "Got more than one %s on host %s" %
                          (binary, args.compute_host))
            sys.exit(-1)
        if service_state.pop().state != 'down':
            syslog.syslog(syslog.LOG_ERR, "Nagios says down, but %s is still "
                          "up in %s when querying nova" %
                          (binary, args.compute_host))
            sys.exit(-1)
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, "Failed to list services %s "
                      "for host %s :: %s" % (binary, args.compute_host, e))
        sys.exit(-1)


# List VMs associated to that compute node which to be evacuated
try:
    vms = nova.servers.list(search_opts={'host': args.compute_host})
except Exception as e:
    syslog.syslog(syslog.LOG_ERR, "Failed to list VMs for host %s :: %s" %
                  (args.compute_host, e))
    sys.exit(-1)


# Get flavor info
flavors_list = nova.flavors.list()
flavors = {}
for flavor in flavors_list:
    flavors[flavor.id] = flavor


def _get_target_host(vm):
    """Two steps to get an available host:
    1. Check if the host is alive
    2. Check the vcpu and memory (act as scheduler)
    3. Check the server group info (affinity/anti-affinity policies)

    [1] From Icehouse, Nova can support server group, see:
    https://blueprints.launchpad.net/nova/+spec/instance-group-api-extension
    [2] From Juno, Nova evacuate can use nova scheduler to get host. see:
    github.com/openstack/nova/commit/d5a70de4793a1e44056c55121505edc63fd36969
    """
    try:
        host_attr = 'OS-EXT-SRV-ATTR:hypervisor_hostname'

        vms = {}
        for i in nova.servers.list():
            vms[i.id] = i

        targets = {}
        for host in nova.hypervisors.list():
            # 1. Make sure it's alive
            if host.state != 'up':
                continue
            # 2. Make sure it can meet the VM's flavor
            vm_flavor = flavors[vm.flavor['id']]
            if vm_flavor.vcpus > host.vcpus or vm_flavor.ram > host.memory_mb:
                continue
            else:
                targets[host.hypervisor_hostname] = host
        # 3. Make sure it respects the affinity/anti-affinity rule
        for group in nova.server_groups.list():
            if vm.id not in group.members:
                continue
            else:
                # Until now(Juno), server group only support affinity and
                # anti-affinity, so it's safe to pick the first one.
                if group.policies[0] == 'affinity':
                    # 3.1 Assume all the members of the server group are
                    # on this (broken) host, then we need to make sure the
                    # target host can meet amount of the vcpus and memory.
                    current_host_group = set()
                    vcpus = 0
                    memory = 0
                    for m in group.members:
                        hostname = vms[m].__dict__[host_attr]
                        current_host_group.add(hostname)
                        vcpus += flavors[vms[m].flavor['id']].vcpus
                        memory += flavors[vms[m].flavor['id']].ram

                    if len(current_host_group) == 2:
                        # This means at least one VM has been evacuated from
                        # the broken host to a new host.
                        return (current_host_group -
                                set([args.compute_host])).pop()
                    elif len(current_host_group) == 1:
                        # This is the first VM of the server group being
                        # evacuate to other host. In other words, all the
                        # server groups members are still on the broken host.
                        for _, host in targets.iteritems():
                            if vcpus < host.vcpus and memory < host.memory_mb:
                                return host.hypervisor_hostname
                elif group.policies[0] == 'anti-affinity':
                    # 3.2 Find a host which is not in host group of current
                    # members
                    anti_affinity_host_group = []
                    for m in group.members:
                        hostname = vms[m].__dict__[host_attr]
                        anti_affinity_host_group.append(hostname)

                    for hypervisor_name, _ in targets.iteritems():
                        if hypervisor_name not in anti_affinity_host_group:
                            return hypervisor_name
                   
                    return None
                break
    except Exception as e:
        syslog.syslog(syslog.LOG_ERR, "Failed to get an available host :: "
                      "%s" % e)
        return None

    # If no affinity associated with the VM, just return the first host
    return None if not targets else targets.keys()[0] 


# Trigger evacuation for each VM
# We collect the results to build a final report
results = {'success': [], 'failures': []}
for vm in vms:
    target = _get_target_host(vm)
    if not target:
        results['failures'].append((vm.name, 'Failed to get a host.'))
        syslog.syslog("Failed to get a host for '%s'" % vm.name)
        continue
    syslog.syslog("Evacuating '%s' to compute host '%s'" % (vm.name, target))
    try:
        success = False
        vm.evacuate(target, True)
        # wait for ACTIVE, or give up after 30 seconds
        start = datetime.now()
        cvm = nova.servers.list(search_opts={'name': vm.name})
        while datetime.now() < (start + timedelta(seconds=args.wait_timeout)):
            if cvm[0].status == 'ACTIVE':
                results['success'].append((vm.name, target))
                break
            time.sleep(3)
            cvm = nova.servers.list(search_opts={'name': vm.name})
        if cvm[0].status != 'ACTIVE':
            results['failures'].append((vm.name, "VM is in ERROR or UNKNOWN "
                                        "status, needs manual migration"))
    except Exception as e:
        results['failures'].append((vm.name, str(e)))
        syslog.syslog(syslog.LOG_ERR, "Failed to evacuate vm '%s' :: %s" %
                      (vm.name, e))

syslog.syslog(syslog.LOG_ERR, "Evacuation of %s :: Successes (%d, %s) :: "
              "Failures (%d, %s)" % (args.compute_host,
                                     len(results['success']),
                                     results['success'],
                                     len(results['failures']),
                                     results['failures']))
