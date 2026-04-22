#!/bin/bash
# Network troubleshooting script
set -euo pipefail

echo "=== Interfaces ==="
ip addr show

echo ""
echo "=== Routes ==="
ip route show

echo ""
echo "=== DNS Resolution ==="
resolvectl status 2>/dev/null || cat /etc/resolv.conf

echo ""
echo "=== Connectivity Test ==="
ping -c 3 1.1.1.1 || echo "ICMP to 1.1.1.1 failed"
ping -c 3 google.com || echo "DNS resolution or ICMP to google.com failed"
