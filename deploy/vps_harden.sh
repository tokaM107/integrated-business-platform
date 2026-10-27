#!/usr/bin/env bash
# Close the VPS's management ports to the internet, reversibly, without touching the five Coolify applications.
# Read before running: docs/PRODUCTION_DEPLOYMENT_COOLIFY.md, section 13. NOT run by the preparation.
#
# What it does (as root on the VPS):
#   1. Starts a dead-man's switch: in REVERT_MINUTES (10) the rules are removed again, unless `vps_harden.sh confirm`
#      was run from a NEW SSH session that worked after the change. A lock-out undoes itself.
#   2. Docker publishes ports around UFW, so the block is in iptables' DOCKER-USER chain (what Docker leaves to the
#      administrator): new connections from the public interface to 8000 (Coolify), 8080 (Traefik's unused dashboard
#      port), 6001 and 6002 (Coolify realtime) are dropped. 80, 443 (the apps, through Traefik) and 22 are untouched.
#   3. UFW for the host itself: 22, 80, 443 allowed, the rest denied (sshd is the only host service listening).
#   4. Persists the DOCKER-USER rules in /etc/ufw/after.rules so a reboot keeps them.
#   Not here (separate, after the owner confirms their key works): sshd PasswordAuthentication no.
#
#   bash vps_harden.sh apply      # then open a NEW terminal, ssh in, open https://<an app domain>; if both work:
#   bash vps_harden.sh confirm    # cancels the automatic revert
#   bash vps_harden.sh revert     # undo everything now
#   bash vps_harden.sh status
set -euo pipefail
IFACE="${IFACE:-$(ip -o -4 route show default | awk '{print $5}' | head -1)}"
PORTS="${PORTS:-8000,8080,6001,6002}"
REVERT_MINUTES="${REVERT_MINUTES:-10}"
MARK="imed-harden"
STATE=/var/run/imed-harden-revert.pid

rules_add() {
	iptables -C DOCKER-USER -i "$IFACE" -p tcp -m multiport --dports "$PORTS" -m conntrack --ctstate NEW -m comment --comment "$MARK" -j DROP 2>/dev/null \
		|| iptables -I DOCKER-USER 1 -i "$IFACE" -p tcp -m multiport --dports "$PORTS" -m conntrack --ctstate NEW -m comment --comment "$MARK" -j DROP
}
rules_del() {
	while iptables -C DOCKER-USER -i "$IFACE" -p tcp -m multiport --dports "$PORTS" -m conntrack --ctstate NEW -m comment --comment "$MARK" -j DROP 2>/dev/null; do
		iptables -D DOCKER-USER -i "$IFACE" -p tcp -m multiport --dports "$PORTS" -m conntrack --ctstate NEW -m comment --comment "$MARK" -j DROP
	done
}
persist() {
	# UFW re-applies after.rules on boot; our chain rules go in a block of their own.
	sed -i "/# $MARK start/,/# $MARK end/d" /etc/ufw/after.rules
	cat >> /etc/ufw/after.rules <<RULES
# $MARK start
*filter
:DOCKER-USER - [0:0]
-I DOCKER-USER 1 -i $IFACE -p tcp -m multiport --dports $PORTS -m conntrack --ctstate NEW -m comment --comment "$MARK" -j DROP
COMMIT
# $MARK end
RULES
}
unpersist() { sed -i "/# $MARK start/,/# $MARK end/d" /etc/ufw/after.rules; }

case "${1:-status}" in
apply)
	echo "interface $IFACE, ports $PORTS; automatic revert in $REVERT_MINUTES minutes unless confirmed"
	nohup bash -c "sleep $((REVERT_MINUTES * 60)); bash '$0' revert; echo 'auto-reverted' >> /var/log/imed-harden.log" >/dev/null 2>&1 &
	echo $! > "$STATE"
	rules_add
	ufw --force reset >/dev/null
	ufw default deny incoming >/dev/null; ufw default allow outgoing >/dev/null
	ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
	ufw --force enable >/dev/null
	persist
	echo "applied $(date -u +%FT%TZ)" >> /var/log/imed-harden.log
	echo "applied. Now, from a NEW terminal: ssh in, open an app domain over https, open http://<ip>:8000 (must fail). Then: bash $0 confirm"
	;;
confirm)
	[ -f "$STATE" ] && kill "$(cat "$STATE")" 2>/dev/null && rm -f "$STATE" && echo "automatic revert cancelled; rules stay" || echo "no pending revert"
	echo "confirmed $(date -u +%FT%TZ)" >> /var/log/imed-harden.log
	;;
revert)
	[ -f "$STATE" ] && kill "$(cat "$STATE")" 2>/dev/null; rm -f "$STATE"
	rules_del; unpersist
	ufw --force disable >/dev/null
	echo "reverted $(date -u +%FT%TZ)" >> /var/log/imed-harden.log
	echo "reverted: DOCKER-USER rules removed, ufw disabled (as before)"
	;;
status)
	echo "interface $IFACE"; iptables -S DOCKER-USER | grep "$MARK" || echo "no $MARK rule"; ufw status | head -8
	;;
*) echo "usage: $0 apply|confirm|revert|status"; exit 2 ;;
esac
