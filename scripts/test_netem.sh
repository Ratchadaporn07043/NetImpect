#!/bin/bash
# ทดสอบว่า tc/netem ใช้งานได้จริงใน container (ต้องรันด้วย cap_add: NET_ADMIN)
# ใช้แบบ: ./scripts/test_netem.sh add|clear <interface>
# ตัวอย่าง: ./scripts/test_netem.sh add eth0

set -e

ACTION=${1:-add}
IFACE=${2:-eth0}

if [ "$ACTION" = "add" ]; then
  echo ">> เพิ่ม delay 300ms + jitter 50ms + packet loss 5% บน $IFACE"
  tc qdisc add dev "$IFACE" root netem delay 300ms 50ms loss 5%
  echo ">> เสร็จแล้ว ลอง ping ออกไปดู latency ที่เปลี่ยนไป"
  tc qdisc show dev "$IFACE"

elif [ "$ACTION" = "clear" ]; then
  echo ">> ลบ netem rule ออกจาก $IFACE (กลับเป็น baseline)"
  tc qdisc del dev "$IFACE" root netem || echo "   (ไม่มี rule อยู่ก่อนแล้ว)"
  tc qdisc show dev "$IFACE"

else
  echo "usage: $0 [add|clear] [interface]"
  exit 1
fi