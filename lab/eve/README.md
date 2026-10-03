# EVE-NG lab export

Place `rootiq.unl` here after exporting the lab from EVE-NG.

Required nodes (topology 2.1):
- R1 — Cisco vIOS, 1GB
- SW1 / SW2 — Cisco vIOS-L2, 1GB each
- APP-01 — Ubuntu 24.04, 2GB, 2 vCPU
- COLLECTOR-01 — Ubuntu 24.04, 2GB, 2 vCPU + Cloud0 (mgmt ens4)
- NAT (temporary for package install)

Images (on EVE host under `/opt/unetlab/addons/qemu/`):
- `vios-adventerprisek9-m.SPA.159-3.M`
- `viosl2-adventerprisek9-m.SSA.high_iron`
- `linux-ubuntu-24.04-server`

Host needs ≥ 16GB RAM. RootIQ reports a waiting state until this live lab is reachable.
