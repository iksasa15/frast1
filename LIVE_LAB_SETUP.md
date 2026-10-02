# Current EVE-NG live-lab contract

This file is the deployment contract for the current four-node lab. Interface names are the IOL names already observed in the lab.

| Node | Interface | Address / VLAN | Connected to |
|---|---|---|---|
| R1 | Ethernet0/0 | 10.10.10.1/24 | SW1 Ethernet0/0 |
| R1 | Ethernet0/1 | 10.10.20.1/24 | SW2 Ethernet0/0 |
| SW1 | Ethernet0/1 | access VLAN 10 | APP-01 ens3 |
| SW2 | Ethernet0/1 | access VLAN 20 | COLLECTOR-01 ens3 |
| COLLECTOR-01 | ens4 | DHCP | EVE NAT/cloud |

## R1

```text
configure terminal
hostname R1
ip domain name rootiq.lab
cdp run
lldp run

interface Ethernet0/0
 description TO-SW1
 ip address 10.10.10.1 255.255.255.0
 no shutdown
 lldp transmit
 lldp receive

interface Ethernet0/1
 description TO-SW2
 ip address 10.10.20.1 255.255.255.0
 no shutdown
 lldp transmit
 lldp receive

username rootiq privilege 15 secret REPLACE_WITH_A_STRONG_PASSWORD
crypto key generate rsa modulus 2048
ip ssh version 2
line vty 0 4
 login local
 transport input ssh
end
write memory
```

## SW1

```text
configure terminal
hostname SW1
ip domain name rootiq.lab
cdp run
lldp run
vlan 10
 name APP-NET

interface Ethernet0/0
 description TO-R1
 switchport mode access
 switchport access vlan 10
 no shutdown

interface Ethernet0/1
 description TO-APP-01
 switchport mode access
 switchport access vlan 10
 no shutdown
 lldp transmit
 lldp receive

interface Vlan10
 ip address 10.10.10.2 255.255.255.0
 no shutdown

ip default-gateway 10.10.10.1
username rootiq privilege 15 secret REPLACE_WITH_A_STRONG_PASSWORD
crypto key generate rsa modulus 2048
ip ssh version 2
line vty 0 4
 login local
 transport input ssh
end
write memory
```

## SW2

```text
configure terminal
hostname SW2
ip domain name rootiq.lab
cdp run
lldp run
vlan 20
 name COLLECTOR-NET

interface Ethernet0/0
 description TO-R1
 switchport mode access
 switchport access vlan 20
 no shutdown

interface Ethernet0/1
 description TO-COLLECTOR-01
 switchport mode access
 switchport access vlan 20
 no shutdown
 lldp transmit
 lldp receive

interface Vlan20
 ip address 10.10.20.2 255.255.255.0
 no shutdown

ip default-gateway 10.10.20.1
username rootiq privilege 15 secret REPLACE_WITH_A_STRONG_PASSWORD
crypto key generate rsa modulus 2048
ip ssh version 2
line vty 0 4
 login local
 transport input ssh
end
write memory
```

## Ubuntu endpoints

Install LLDP on APP-01 and COLLECTOR-01 so the access links are observed rather than guessed:

```bash
sudo apt update
sudo apt install -y lldpd
sudo systemctl enable --now lldpd
sudo lldpcli show neighbors
```

APP-01 uses `10.10.10.10/24` with default gateway `10.10.10.1`. COLLECTOR-01 uses `10.10.20.10/24` on `ens3`; if `ens4` supplies the Internet default route, add an explicit route for the application subnet:

```yaml
network:
  version: 2
  ethernets:
    ens3:
      addresses: [10.10.20.10/24]
      routes:
        - to: 10.10.10.0/24
          via: 10.10.20.1
    ens4:
      dhcp4: true
```

Apply with `sudo netplan try`, then `sudo netplan apply`.

## Verification gate

Do not start the application until these checks pass:

```text
R1# show ip interface brief
R1# show cdp neighbors detail
R1# show lldp neighbors detail
SW1# show ip interface brief
SW2# show ip interface brief
```

```bash
ping -c 2 10.10.20.1
ping -c 2 10.10.20.2
ping -c 2 10.10.10.1
ping -c 2 10.10.10.2
ssh rootiq@10.10.20.1
```

After the collector starts, verify the contract from the server:

```bash
curl -s http://SERVER_IP:8000/api/health
curl -s http://SERVER_IP:8000/api/topology
```

The health response must show `discovery.state` as `live`. A `degraded` state with an error is actionable; do not hide it by adding static nodes.
