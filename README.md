# BGP EVPN/VXLAN Data Center Fabric Lab

Complete spine-leaf BGP EVPN/VXLAN fabric built on Cisco NX-OS 10.6.1
with full Ansible automation.

## Topology
- 2 Spines (Cisco N9K-C9500v) — Route Reflectors
- 5 Leaves (Cisco N9K-C9300v) — including 1 border leaf
- 2 vPC pairs (LEAF-01/02 and LEAF-03/04)
- 2 Tenants (TENANT-A and TENANT-B)
- External routing via R-ISP and SW

## Modules completed
- Module 1: OSPF Underlay
- Module 2: BGP EVPN Overlay
- Module 3: VXLAN L2 VNI
- Module 4: Symmetric IRB + Anycast Gateway
- Module 5+6: vPC Dual-Homing
- Module 7: Border Leaf + eBGP
- Module 8: End-to-End Verification (16/16 tests)
- Module 9: Full Ansible Automation

## Quick Start
ansible-playbook m9/deploy_fabric.yml --skip-tags wipe

## Test Suite
ansible-playbook m9/deploy_fabric.yml --tags verify

## Author
Abdelkrim Bari — CCIE #20869
