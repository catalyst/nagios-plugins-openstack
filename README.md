nagios-plugins-openstack
============

## Description

Nagios probes to monitor an openstack cluster.

==============

Overview
--------

Deb package and PPA (example for 20140710 and catalystit/openstack)
-----------

```
cd ..
tar zcvf nagios-plugins-openstack_1.20140710.orig.tar.gz nagios-plugins-openstack
cd nagios-plugins-openstack
dpkg-buildpackage -rfakeroot -d -us -uc -S
cd ..
dput -f ppa:catalystit/openstack nagios-plugins-openstack_1.20140710-1_amd64.changes
```


