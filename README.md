# BGP EVPN/VXLAN Dual Data Center PoC

## Overview

Enterprise-grade dual data center BGP EVPN/VXLAN proof-of-concept lab built in EVE-NG. This project demonstrates a full fabric deployment across two data centers — DC1 running Cisco Nexus NX-OS and DC2 running Arista vEOS — with complete Ansible automation for each module.

**Author:** Abdel — CCIE #20869  
**Organization:** [Bari Network Consulting](https://github.com/Bari-network-consulting)  
**Platform:** EVE-NG  
**Automation:** Ansible + AWX (192.168.1.102)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DC1 — Cisco Nexus                           │
│                         AS 65000 / NX-OS 10.6.1                     │
│                                                                     │
│         N-SPINE-01 (.10)          N-SPINE-02 (.11)                  │
│              │   │   │   │   │        │   │   │   │   │             │
│         ─────┼───┼───┼───┼───┼────────┼───┼───┼───┼───┼─────       │
│              │   │   │   │   │        │   │   │   │   │             │
│  N-LEAF-01 (.12) N-LEAF-02 (.13) N-LEAF-03 (.14) N-LEAF-04 (.15)   │
│  [vPC domain 10  ─────────────]  [vPC domain 20  ─────────────]     │
│       │   │                            │   │                        │
│  SRV1-TEN-A  SRV1-TEN-B          SRV2-TEN-A  SRV2-TEN-B            │
│  10.10.10.11 10.20.20.11         10.10.10.21 10.20.20.21            │
│                                                                     │
│              N-LEAF-05 (.16) — Border Leaf                          │
│              │        │                                             │
│         PaloAlto-FW1  DCI Link (E1/6)                               │
└─────────────────────────────────────────────────────────────────────┘
                              │ DCI
                    N-LEAF-05 E1/6 ↔ A-LEAF-05 Eth6
                              │
┌─────────────────────────────────────────────────────────────────────┐
│                         DC2 — Arista vEOS                           │
│                         AS 65200 / EOS 4.28.1F                      │
│                                                                     │
│         A-SPINE-01 (.30)          A-SPINE-02 (.31)                  │
│              │   │   │   │   │        │   │   │   │   │             │
│         ─────┼───┼───┼───┼───┼────────┼───┼───┼───┼───┼─────       │
│              │   │   │   │   │        │   │   │   │   │             │
│  A-LEAF-01 (.32) A-LEAF-02 (.33) A-LEAF-03 (.34) A-LEAF-04 (.35)   │
│  [ESI pair 1     ─────────────]  [ESI pair 2  ────────────────]     │
│       │   │                            │   │                        │
│   A-SRV-1    A-SRV-2             A-SRV-3    A-SRV-4                 │
│  10.30.10.11 10.40.20.11        10.30.10.21 10.40.20.21             │
│                                                                     │
│              A-LEAF-05 (.36) — Border Leaf                          │
│              │        │                                             │
│         Fortinet-FW2  DCI Link (Eth6)                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## IP Addressing

### Management Network — 192.168.1.0/24

| Device | IP | Role |
|---|---|---|
| N-SPINE-01 | 192.168.1.10 | DC1 Spine |
| N-SPINE-02 | 192.168.1.11 | DC1 Spine |
| N-LEAF-01 | 192.168.1.12 | DC1 Leaf / vPC pair 1 |
| N-LEAF-02 | 192.168.1.13 | DC1 Leaf / vPC pair 1 |
| N-LEAF-03 | 192.168.1.14 | DC1 Leaf / vPC pair 2 |
| N-LEAF-04 | 192.168.1.15 | DC1 Leaf / vPC pair 2 |
| N-LEAF-05 | 192.168.1.16 | DC1 Border Leaf |
| R-ISP | 192.168.1.17 | External Router AS65500 |
| SW | 192.168.1.18 | Access Switch |
| A-SPINE-01 | 192.168.1.30 | DC2 Spine |
| A-SPINE-02 | 192.168.1.31 | DC2 Spine |
| A-LEAF-01 | 192.168.1.32 | DC2 Leaf / ESI pair 1 |
| A-LEAF-02 | 192.168.1.33 | DC2 Leaf / ESI pair 1 |
| A-LEAF-03 | 192.168.1.34 | DC2 Leaf / ESI pair 2 |
| A-LEAF-04 | 192.168.1.35 | DC2 Leaf / ESI pair 2 |
| A-LEAF-05 | 192.168.1.36 | DC2 Border Leaf |
| PaloAlto-FW1 | 192.168.1.40 | DC1 N-S Firewall |
| PaloAlto-FW2 | 192.168.1.44 | DC2 E-W Firewall |
| A-SRV-1 | 192.168.1.50 | DC2 Server TENANT-A |
| A-SRV-2 | 192.168.1.51 | DC2 Server TENANT-B |
| A-SRV-3 | 192.168.1.53 | DC2 Server TENANT-A |
| A-SRV-4 | 192.168.1.52 | DC2 Server TENANT-B |
| SRV1-TEN-A | 192.168.1.54 | DC1 Server TENANT-A |
| SRV1-TEN-B | 192.168.1.55 | DC1 Server TENANT-B |
| SRV2-TEN-A | 192.168.1.56 | DC1 Server TENANT-A |
| SRV2-TEN-B | 192.168.1.57 | DC1 Server TENANT-B |
| Fortinet-FW1 | 192.168.1.58 | DC1 E-W Firewall |
| Fortinet-FW2 | 192.168.1.59 | DC2 N-S Firewall |
| BIGIP-LB1 | 192.168.1.71 | DC1 Load Balancer |
| BIGIP-LB2 | 192.168.1.72 | DC2 Load Balancer |
| AWX/Ansible | 192.168.1.102 | Automation Server |

### DC1 Underlay — Loopbacks

| Device | Loopback0 | Loopback1 | Anycast VTEP |
|---|---|---|---|
| N-SPINE-01 | 10.0.0.1/32 | — | — |
| N-SPINE-02 | 10.0.0.2/32 | — | — |
| N-LEAF-01 | 10.0.0.11/32 | 10.0.0.111/32 | 10.0.0.200/32 |
| N-LEAF-02 | 10.0.0.12/32 | 10.0.0.112/32 | 10.0.0.200/32 |
| N-LEAF-03 | 10.0.0.13/32 | 10.0.0.113/32 | 10.0.0.201/32 |
| N-LEAF-04 | 10.0.0.14/32 | 10.0.0.114/32 | 10.0.0.201/32 |
| N-LEAF-05 | 10.0.0.15/32 | 10.0.0.115/32 | — |

### DC2 Underlay — Loopbacks

| Device | Loopback0 | Loopback1 |
|---|---|---|
| A-SPINE-01 | 10.1.0.1/32 | — |
| A-SPINE-02 | 10.1.0.2/32 | — |
| A-LEAF-01 | 10.1.0.11/32 | 10.1.0.111/32 |
| A-LEAF-02 | 10.1.0.12/32 | 10.1.0.112/32 |
| A-LEAF-03 | 10.1.0.13/32 | 10.1.0.113/32 |
| A-LEAF-04 | 10.1.0.14/32 | 10.1.0.114/32 |
| A-LEAF-05 | 10.1.0.15/32 | 10.1.0.115/32 |

### Tenant Design

| Tenant | VRF | VLAN | L2 VNI | L3 VNI | DC1 Subnet | DC2 Subnet |
|---|---|---|---|---|---|---|
| TENANT-A | TENANT-A | 10 | 10010 | 50001 | 10.10.10.0/24 | 10.30.10.0/24 |
| TENANT-B | TENANT-B | 20 | 10020 | 50002 | 10.20.20.0/24 | 10.40.20.0/24 |

---

## Module Status

### DC1 — Cisco Nexus (AS 65000)

| Module | Description | Status | Tests |
|---|---|---|---|
| 01 | OSPF Underlay | ✅ Complete | 7/7 FULL |
| 02 | BGP EVPN Overlay | ✅ Complete | 7/7 Established |
| 03 | VXLAN L2 VNI | ✅ Complete | — |
| 04 | Symmetric IRB | ✅ Complete | — |
| 05 | vPC Pair 1 (N-LEAF-01/02) | ✅ Complete | — |
| 06 | vPC Pair 2 (N-LEAF-03/04) | ✅ Complete | — |
| 07 | Border Leaf eBGP | ✅ Complete | pending PaloAlto |
| 08 | End-to-End Verify | ⚠️ Partial | 8/16 pass |
| 09 | Deploy All | ✅ Complete | master playbook |

> Tests 9-16 pending PaloAlto-FW1 configuration (Phase 4)

### DC2 — Arista vEOS (AS 65200)

| Module | Description | Status | Tests |
|---|---|---|---|
| 01 | OSPF Underlay | ✅ Complete | 7/7 FULL |
| 02 | BGP EVPN Overlay | ✅ Complete | 7/7 Established |
| 03 | VXLAN L2 VNI | ✅ Complete | — |
| 04 | Symmetric IRB | ✅ Complete | — |
| 05 | ESI Multihoming | ✅ Complete | Po1/2/3/4 Up |
| 06 | Border Leaf eBGP | ✅ Complete | pending Fortinet |
| 07 | End-to-End Verify | ✅ Complete | 6/6 pass |
| 08 | Deploy All | ✅ Complete | master playbook |

---

## Phase Roadmap

```
Phase 1  ✅  DC1 Cisco Nexus fabric
Phase 2  ✅  DC2 Arista vEOS fabric
Phase 3  🔄  DCI L3 interconnect (N-LEAF-05 ↔ A-LEAF-05)
Phase 4  ⏳  Security stack (PaloAlto + Fortinet)
Phase 5  ⏳  F5 BIG-IP load balancing
Phase 6  ⏳  Customer IPsec VPN
```

---

## Project Structure

```
evpn-vxlan-lab/
├── dc1/                          # DC1 Cisco Nexus automation
│   ├── ansible.cfg
│   ├── inventory/hosts.ini
│   ├── group_vars/
│   │   ├── dc1_fabric.yml        # NX-OS credentials + tenant definitions
│   │   └── dc1_ios.yml           # IOS server credentials
│   ├── host_vars/                # Per-device variables
│   │   ├── N-SPINE-01/02.yml
│   │   ├── N-LEAF-01/02/03/04/05.yml
│   │   └── SRV*/PC*.yml
│   ├── module01_ospf_underlay.yml
│   ├── module02_bgp_evpn.yml
│   ├── module03_vxlan_l2vni.yml
│   ├── module04_symmetric_irb.yml
│   ├── module05_vpc_pair1.yml
│   ├── module06_vpc_pair2.yml
│   ├── module07_border_leaf.yml
│   ├── module08_verify.yml       # 16-test verification suite
│   └── module09_deploy_all.yml   # Master playbook
│
├── dc2/                          # DC2 Arista vEOS automation
│   ├── ansible.cfg
│   ├── inventory/hosts.ini
│   ├── group_vars/
│   │   ├── dc2_fabric.yml        # EOS httpapi credentials + tenant definitions
│   │   └── dc2_ios.yml           # IOS server credentials
│   ├── host_vars/                # Per-device variables
│   │   ├── A-SPINE-01/02.yml
│   │   ├── A-LEAF-01/02/03/04/05.yml
│   │   └── A-SRV-*.yml
│   ├── module01_ospf_underlay.yml
│   ├── module02_bgp_evpn.yml
│   ├── module03_vxlan_l2vni.yml
│   ├── module04_symmetric_irb.yml
│   ├── module05_esi_multihoming.yml
│   ├── module06_border_leaf.yml
│   ├── module07_verify.yml       # 6-test verification suite
│   └── module08_deploy_all.yml   # Master playbook
│
└── m9/                           # Legacy DC1 project (reference only)
```

---

## Quick Start

### Prerequisites
- EVE-NG with topology loaded
- Ansible server at 192.168.1.102
- AWX at http://192.168.1.102

### Deploy DC1

```bash
cd ~/evpn-lab/dc1
ansible-playbook module09_deploy_all.yml
```

### Deploy DC2

```bash
cd ~/evpn-lab/dc2
ansible-playbook module08_deploy_all.yml
```

### Run individual modules

```bash
# DC1 example
cd ~/evpn-lab/dc1
ansible-playbook module01_ospf_underlay.yml

# DC2 example
cd ~/evpn-lab/dc2
ansible-playbook module01_ospf_underlay.yml
```

### Verify connectivity

```bash
# DC1 — 16-test suite
cd ~/evpn-lab/dc1
ansible-playbook module08_verify.yml

# DC2 — 6-test suite
cd ~/evpn-lab/dc2
ansible-playbook module07_verify.yml
```

---

## Key Technical Details

### DC1 vs DC2 Differences

| Feature | DC1 Cisco NX-OS | DC2 Arista vEOS |
|---|---|---|
| Ansible connection | network_cli | httpapi (port 80) |
| Server multihoming | vPC | ESI (RFC 7432) |
| VTEP interface | nve1 | Vxlan1 |
| Anycast gateway | fabric forwarding anycast-gateway | ip virtual-router mac-address |
| L3 VNI binding | member vni X associate-vrf | vxlan vrf X vni Y |
| OSPF passive | per-interface | passive-interface default + exceptions |

### Known NX-OS Quirks
- `ip routing vrf X` is invalid — routing enabled automatically per VRF
- `associate-vrf` must be inline: `member vni 50001 associate-vrf`
- vPC peer-link requires `channel-group X force mode active`
- Legacy SSH algorithms required: `KexAlgorithms +diffie-hellman-group14-sha1`

### Known Arista vEOS Quirks
- `show port-channel summary` deprecated → use `show port-channel dense`
- `show vxlan interface` invalid → use `show interfaces Vxlan1`
- Loopbacks require explicit `ip ospf area 0.0.0.0`
- Management interface must NOT be configured by Ansible

---

## Tags

| Tag | Description |
|---|---|
| v1.0 | DC1 Modules 1-9 complete |
| v2.0 | DC1 + DC2 fabric complete |

---

## License

Private repository — Bari Network Consulting
