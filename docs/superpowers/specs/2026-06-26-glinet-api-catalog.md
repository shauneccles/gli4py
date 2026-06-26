# GL.iNet RPC API catalog (research reference)

Companion to `2026-06-26-glinet-api-enumerator-design.md`. This is the consolidated,
sourced surface map that seeds `gli4py/enumerator/catalog.py`, `wordlist.py`, and the
risk classification. It merges three research sweeps with a live read-only enumeration.

**Wire form:** `{"method":"call","params":[sid, service, method, args]}`. Internal spec keys
use underscores (`wg_client`); the wire uses hyphens (`wg-client`) — the catalog stores the
hyphenated canonical form.

**Tags:** `R` read (no side effects) · `W` write (mutates config) · `D` dangerous
(destructive/disruptive) · `A` active-read (read but causes a transient effect, e.g. `scan`).
`★` = confirmed present on the live test device (read-only probe). `[wrapped]` = already
exposed by `gli4py`.

**Primary sources:** `tomtana/python-glinet` `api_description.json` (42 services, authoritative);
`HarvsG/gli4py`; `spusuf/glinet_api-hass`; `angolo40/GLiNet_HomeAssistant`;
`vithurshanselvarajah/ha-glinet`; `ryanrishi/glinet-client-go`; `cinderblock/homeassistant-glinet`;
`CaseyBlackburn/glsms`; OpenWRT `rpcd`/`luci` ACL files & ubus docs.

## Auth (called directly, not via `call`)

| Method | Tag | Notes |
|---|---|---|
| `challenge` | R | `{username}` → `{alg, salt, nonce, hash-method}` |
| `login` | W | `{username, hash}` → `{sid}` |
| `logout` | W | `{sid}` |
| `alive` | R | session keep-alive |

## GL.iNet application services

### system ★ [wrapped: get_info, get_status, get_load, reboot]
`get_info` R★ · `get_status` R★ · `get_load` R★ · `disk_info` R★ · `get_timezone_config` R★ ·
`get_unixtime` R★ · `get_httpd_mem_status` R★ · `get_security_policy` R★ · `get_percent` R ·
`set_timezone_config` W · `set_security_policy` W · `set_password` D · `add_user` W ·
`remove_user` W · `reset_firmware` D · `reboot` D

### wifi ★ [wrapped: get_config (+ wifi_ifaces_get/set_enabled)]
`get_config` R★ · `get_status` R★ · `get_mlo_config` R★ · `set_config` W · `set_txpower` W · `set_mlo_config` W

### clients ★ [wrapped: get_list (+ connected_clients)]
`get_list` R★ · `get_status` R★ · `block_client` W · `remove_offline` W · `set_info` W · `clear_cache` W

### lan ★ [wrapped: get_static_bind_list]
`get_static_bind_list` R★ · `get_config_list` R★ · `set_config` W · `add_static_bind` W · `set_static_bind` W · `remove_static_bind` W

### macclone [wrapped: get_mac]
`get_mac` R · `set_mac` W

### edgerouter ★ [wrapped: get_status/status (connected_to_internet)]
`get_status`/`status` R★ · `get_config` R★ · `scan` A · `set_config` W · `set_devices` W

### network ★
`get_arp_list` R★ · `get_dhcp_leases` R · `routes` R · `routes6` R · `check_wan_cable` R

### cable ★
`get_status` R★ · `get_config` R★ · `set_config` W · `change_interface` W

### repeater ★
`get_config` R★ · `get_status` R★ · `get_saved_ap_list` R★ · `scan` A · `connect` W · `disconnect` W ·
`set_config` W · `forget` W · `remove_saved_ap` W · `enter_bare_mode` W · `exit_bare_mode` W

### tethering ★
`get_status` R★ · `set_connect` W · `disconnect` W

### modem ★ (cellular models)
`get_info` R · `get_status` R · `get_config` R · `get_cells_info` R · `get_sms_list` R ·
`get_traffic_config` R★ · `get_debug_msg` R · `set_connect` W · `disconnect` W · `set_auto_connect` W ·
`send_at_command` D · `reboot_modem` D · `send_sms` W · `set_sms` W · `remove_sms` W ·
`reset_traffic_count` W · `set_traffic_auto_save` W

### wg-client ★ [wrapped: get_status, get_all_config_list, start, stop]
`get_status` R · `get_all_config_list` R★ · `get_config_list` R · `get_group_list` R★ · `get_setting` R ·
`get_route_list` R · `get_recommend_config` R · `get_third_config` R · `check_config` R ·
`start` W · `stop` W · `add_config` W · `set_config` W · `remove_config` W · `clear_config_list` W ·
`confirm_config` W · `add_group` W · `set_group` W · `remove_group` W · `set_proxy` W ·
`set_setting` W · `add_route`/`set_route`/`remove_route` W

### wg-server ★
`get_status` R★ · `get_config` R★ (→ `private_key`!) · `get_peer_list` R★ · `get_route_list` R★ · `get_setting` R★ ·
`start` W · `stop` W · `set_config` W · `add_peer` W · `set_peer` W · `remove_peer` W ·
`generate_peer` W · `generate_key` W · `generate_publickey` W · `set_setting` W · `add_route`/`set_route`/`remove_route` W

### ovpn-client ★
`get_status` R · `get_all_config_list` R★ · `get_config_list` R · `get_group_list` R★ · `get_setting` R ·
`get_route_list` R · `get_recommend_config` R · `get_third_config` R · `check_config` R ·
`start` W · `stop` W · `add_config`/`set_config`/`remove_config`/`clear_config_list` W ·
`confirm_config` W · `add_group`/`set_group`/`remove_group` W · `set_setting` W · `*_route` W

### ovpn-server ★
`get_status` R★ · `get_config` R★ (→ `ca`/`cert`/`dh`/`ta`/`key`!) · `get_user_list` R★ · `get_route_list` R★ · `get_setting` R★ ·
`start` W · `stop` W · `set_config` W · `generate_certificate` W · `export_config` R · `add_user` W · `remove_user` W · `set_setting` W · `*_route` W

### vpn-client ★ [wrapped: get_status, set_tunnel (FW ≥4.8)]
`get_status` R★ · `get_tunnel` R · `set_tunnel` W

### vpn-policy
`get_global_policy` R · `get_proxy_mode` R · `get_domain_policy` R · `get_mac_policy` R · `get_vlan_policy` R ·
`set_global_policy`/`set_proxy_mode`/`set_domain_policy`/`set_mac_policy`/`set_vlan_policy` W

### tailscale ★ [wrapped: get_status, get_config, set_config (+ start/stop/state)]
`get_status` R★ · `get_config` R★ · `set_config` W

### zerotier ★
`get_config` R★ · `get_status` R★ · `set_config` W

### tor ★
`get_config` R★ · `get_status` R★ · `set_config` W · `replace_country` W

### parental-control ★
`get_config` R★ · `get_status` R · `get_brief` R · `get_mode` R · `set_config`/`set_brief`/`set_group`/`set_mode`/`update` W

### bark
`set_config` W (content filtering; no documented read)

### adguardhome ★
`get_config` R★ · `set_config` W

### firewall ★
`get_zone_list` R★ · `get_rule_list` R★ · `get_dmz` R★ · `get_port_forward_list` R★ · `get_wan_access` R★ ·
`get_acl_rule_list` R★ · `get_acl_zone_list` R · `add_rule`/`set_rule`/`remove_rule` W · `set_dmz` W ·
`add_port_forward`/`set_port_forward`/`remove_port_forward` W · `set_wan_access` W · `*_acl_rule` W · `order_*` W

### ddns ★
`get_config` R★ (→ `device_id`) · `get_status` R★ · `set_config` W

### dns ★
`get_info` R★ · `get_config` R★ · `get_host` R★ · `set_info`/`set_config`/`set_host` W

### custom_dns
`get_info` R · `set_info` W

### ipv6 ★
`get_ipv6` R★ · `set_ipv6` W

### netmode ★
`get_mode` R★ · `set_mode` W

### upgrade ★
`get_config` R★ · `get_online_upgrade_status` R★ · `check_firmware_online` A (external) · `check_firmware_local` R ·
`set_config` W · `upgrade_online` D · `upgrade_local` D

### reboot (scheduled)
`get_config` R · `set_config` W

### led ★ [candidate #2]
`get_config` R★ · `set_config` W

### fan
`get_status` R · `get_config` R · `set_config` W · `set_status` W

### qos ★
`get_config` R★ · `get_client_list` R★ · `get_device_group` R · `enable_qos`/`set_model`/`*_speed_limit_rule`/`*_device_group`/`set_channel_bandwidth_ratio`/`set_other_client_priority` W

### kmwan ★ (multi-WAN / failover)
`get_status` R★ · `get_config` R★

### acl ★ (router-level)
`get_group_list` R★ · `get_acl_list` R · `add_group`/`remove_group`/`add_acl`/`remove_acl`/`add_user`/`remove_user` W

### plugins ★ (opkg)
`get_repository_status` R★ · `get_list` R · `get_package_info` R · `update_repository` W · `install_package` W · `remove_package` W

### ui ★
`get_lang` R★ · `get_menu_list` R★ · `check_initialized` R★ · `set_lang` W · `load_locales` R · `init` D

### s2s ★ (site-to-site WireGuard)
`get_status` R★ · `set_config` W · `remove_config` W · `start_wg`/`stop_wg` W · `enable_echo_server` W · `generate_wg_genkey` W

### cloud ★ (GoodCloud)
`get_config` R★ · `set_config` W · `unbind` W

### rtty ★ (remote terminal)
`get_config` R★ · `set_config` W · `run` W · `stop` W

### black_white_list ★
`get_config` R★ · `set_config` W · `set_single_mac` W

### mcu (battery/OLED models)
`get_config` R · `get_battery_config` R · `set_config` W · `set_battery_config` W

### diag [wrapped: ping]
`ping` A · `traceroute` A

### logread
`get_uboot_log`/`get_system_log`/`get_kernel_log`/`get_crash_log` R · `get_config` R · `remove_crash_log` W · `export_logs` R · `set_config` W

### nas_web / samba / dlna (NAS models)
`nas_web`: `get_status`/`get_nas_ser`/`get_proto_config`/`get_user_list`/`get_disk_list`/`get_file_list`/`get_share_list` R; mutating `set_*`/`add_*`/`remove_*`/`eject_disk`/`start` W.
`samba`: `get_config` R · `set_config` W. `dlna`: `get_config` R · `set_config` W.

### igmp
`get` R · `set` W

### switch-button
`get_funcs` R · `get_config` R · `set_config` W

### rs485 (industrial models)
`get_rs485_config`/`get_mqtt_config`/`get_socket_config` R · `read_modbus_data` R · `status` R ·
`set_*_config` W · `write_modbus_data` W · `terminal` W · `start`/`stop` W · `glcould_tool` W

### cloud_batch_manage (B2B fleet)
`get_batch_config`/`get_2b_config`/`bind_info` R · `send_router_info`/`set_batch_config`/`set_2b_config`/`designated_customer` W

## Standard OpenWRT ubus (NOT exposed on the live gl-ngx gateway — all `-32601`)

Recorded for the `--dangerous` wordlist and `--discover-acl`; verified blocked on the test device,
but other firmwares/roles may expose some. `network.interface dump` returned `-32602` (lone exception).

Objects: `system` (board/info), `network`, `network.interface` (dump), `network.device` (status),
`network.wireless`, `uci` (get/changes/state), `file` (list/read/stat/md5), `service` (list/state),
`session` (access/get), `log` (read), `iwinfo` (devices/info/assoclist/scan A), `dhcp` (ipv4leases/ipv6leases),
`luci`/`luci-rpc` (getBoardJSON/getHostHints/getNetworkDevices/getWirelessDevices/getFeatures),
`rpc-sys` (packagelist/upgrade_test), `hostapd.<if>` (get_clients).
Dangerous ubus: `system reboot/sysupgrade/factoryreset/watchdog/signal`, `file write/remove/exec`,
`uci commit/apply`, `network.interface up/down`, `service signal`, `rpc-sys upgrade_start/factory/reboot`.

## `--dangerous` wordlist seeds

**Service seeds** (~95): the GL.iNet services above (hyphen + underscore variants) + the OpenWRT ubus
objects above + speculative: `ipsec`, `vpn_dashboard`, `vpn_status`, `dpi`, `stat`, `easymesh`, `sdwan`, `vlan`, `bridge`.

**Read-method seeds:** `get_status get_config get_info get_list get_all_config_list get_config_list
get_group_list get_route_list get_setting get_mac get_mode get_ipv6 get_host get_zone_list
get_rule_list get_port_forward_list get_peer_list get_user_list get_repository_status get_lang
get_menu_list check_initialized status info board list dump state check_config get_data get_log
get_brief get_funcs get_battery_config`

**Active-read seeds (— `--dangerous-full` only):** `scan get_scan_list get_saved_ap_list check_firmware_online assoclist freqlist survey`

**Mutating-method seeds (— `--dangerous-full` only):** `set_config set_status set_tunnel set start stop
restart enable disable connect disconnect add_config remove_config add_group remove_group set_group
add_peer remove_peer set_peer add_route set_route remove_route clear_config_list confirm_config
set_proxy set_setting block_client remove_offline set_info set_mac set_mode set_ipv6 set_host
add_static_bind remove_static_bind set_dmz add_rule set_rule remove_rule add_port_forward
remove_port_forward update install_package remove_package upgrade_online upgrade_local`

**Never brute (DANGEROUS, hard-excluded even from `--dangerous-full` unless `--include-destructive`):**
`reboot reset_firmware factoryreset sysupgrade factory upgrade_start watchdog signal write exec remove
commit apply password_set set_password reboot_modem send_at_command init unbind generate_certificate`

## SSH ground-truth (from the live device — definitive)

`/usr/lib/oui-httpd/rpc/` is the exact handler directory (one file per service). Full listing
from the test device (`.so` = compiled C plugin, others = Lua source; `.so`/underscore variants
are duplicates of the hyphenated service):

```
acl  adguardhome  bark  black_white_list  cable  clients  cloud  ddns(.so)  diag  dns  dpi★NEW
edgerouter  firewall  flow_statistics★NEW  igmp  ipv6  kmwan  lan  led  local-access★NEW  logread
luci  modem(.so)  mptun★NEW  nas-web(.so)  netmode  network  ovpn-client(.so)  ovpn_client
parental-control  plugins(.so)  qos  repeater  rtty  s2s(.so)  sms-forward★NEW  sqm★NEW
srv_conn_check★NEW  system  tailscale  tethering  timer★NEW  tor  ui  upgrade(.so)  vpn-client
wg-client(.so)  wg_client  wifi  zerotier   (+ libcmcollect.so helper)
```

**★NEW services not in the HTTP/research catalog** (add to the catalog seed; methods to be
extracted via `--ssh` and confirmed by probe):
- `dpi` — deep packet inspection / app stats
- `flow_statistics` — per-interface/per-client throughput (the #2 "network throughput" feature)
- `sqm` — Smart Queue Management (QoS/cake)
- `mptun` — multipath tunnel
- `sms-forward` — SMS forwarding (cellular)
- `local-access` — local-access control
- `srv_conn_check` — service connectivity check
- `timer` — scheduled tasks

**Method extraction technique** (read-only, per handler):
- Lua handler → `grep -oE 'function M\.[A-Za-z0-9_]+'` (+ alternate `M.x = function` / `["x"]=function` /
  trailing `return { x = ... }` patterns). E.g. `tor` → `get_config, set_config, get_status`.
- `.so` handler → `strings <file> | grep -E '^(get|set|start|stop|add|remove|list|check|generate|export)_?[a-z0-9_]*$'`,
  then drop internal helpers (e.g. modem.so's `add_event_mgr`, `get_globle_status_manager`). Candidates,
  confirmed by a read-only HTTP probe. E.g. `wg-client.so` → `get_all_config_list, get_config_list,
  get_group_list, add_config, set_config, remove_config, set_proxy, check_config, get_recommend_config,
  get_third_config`; `ovpn-server.so` → `get_config, get_status, get_user_list, get_route_list,
  get_setting, start, stop, set_config, generate_certificate, add_user, remove_user, *_route`.

**Dispatch/ACL** (`/usr/share/gl-ngx/oui-rpc.lua`): `call`→`[sid, object, method, args]`; `object`/`method`
must match `^[%a_][%w%-_]+$`; gated by `rpc.is_no_auth(object,method)` else `rpc.access("rpc",
object.."."..method)` against `/etc/oui/oui.db`. `no-auth-methods` (from `/etc/config/oui-httpd`):
`ui {get_lang, load_locales, check_initialized, init}`, `system {get_timezone_list}`.

**`ubus list` (lower layer, context only):** `cellular.{cm,collect,failover,modem,network,sim,status}`,
`dnsmasq(.dns)`, `gl-clients`, `gl-dpi`, `gl-session`, `file`, `iwinfo`, `log`, `luci(-rpc)`, `network`,
`network.device`, `network.interface(.{lan,wan,wwan,wgserver,secondwan,loopback})`, `network.wireless`,
`rc`, `repeater`, `service`, `session`, `sms_manager`, `system`, `uci`, `mtk-wifi`, many `hotplug.*`.

**Validator schemas — `/usr/share/gl-validator.d/*.lua` (≈26, method names + param schemas):**
`cable clients cloud dns firewall lan modem mptun nas-web netifyd netmode ovpn-client ovpn-server
ovpn_client parental-control plugins repeater s2s sms-forward system ui vpn-client wg-client wg-server
wg_client wifi`. (`netifyd` = the DPI engine — another service.) Richest source for `(method, params)`.

**flow_statistics methods** (from bytecode `strings`): `get_flow_statistics` R · `get_app_flow_statistics` R ·
`get_top_app_flow_statistics` R · `get_statistics_rule` R · `set_statistics_rule` W · `clear_statistics` W
(data in `/tmp/traffic_data.db`, app metadata `/etc/netifyd/app-metadata.json`). This is the #2 "throughput" feature.

**Auth/ACL model — `/etc/oui/oui.db`:** single table `account(username TEXT PK, acl TEXT)`; on the test device
`root → root`. `rpc.lua`: `M.access(scope, entry)` short-circuits **`aclgroup == "root"` ⇒ always allowed**;
else `db.get_perm(aclgroup, scope, entry)`. So a root login enumerates the full surface; per-group
`object.method` grants only constrain limited accounts. Read via on-device `sqlite3` (present) or SFTP+local parse.
`no-auth-methods` (from `/etc/config/oui-httpd`): `ui {get_lang, load_locales, check_initialized, init}`,
`system {get_timezone_list}`. Read-classification hint from `rpc.lua`: methods containing `get`/`load`/`check`
are treated as reads (no NOTICE log) — matches our READ verb heuristic.

