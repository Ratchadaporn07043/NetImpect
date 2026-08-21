"""
Network Controller
===================
Wrapper around tc/netem commands.

Important note about impairment direction, verified from this implementation:
A qdisc attached to an interface's `root` controls **egress** only.
ดังนั้น `tc qdisc add dev eth0 root netem ...` ด้านล่างหน่วง/ทิ้ง/แกว่ง/จำกัด
แบนด์วิดท์เฉพาะแพ็กเก็ตที่ **ออกจาก** container คือ inference request และ TCP
ACK ขาออก ส่วน response body จากโมเดล (ซึ่งมักใหญ่กว่า request มาก) เดินทางเข้า
มาทาง ingress ที่ **ไม่ถูก shape เลย** และได้รับผลกระทบทางอ้อมผ่าน transport
coupling เท่านั้น

This file has no ingress qdisc, IFB device, or mirred redirect. All measurements
in this project are therefore egress-only and must be reported as such; do not
describe them as symmetric shaping (see
`Paper/NetImpact.md/Current/NetImpact_18_Implementation_Verification_Addendum.md` §1)
การเพิ่ม ingress+IFB เป็นรายการ future work ที่ระบุไว้ใน
`Paper/NetImpact.md/Current/NetImpact_07_Paper_Positioning.md`
"""

import subprocess


class NetworkController:
    def __init__(self, iface: str = "eth0"):
        self.iface = iface

    def _run(self, cmd: list):
        result = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "cmd": " ".join(cmd),
        }

    def clear(self):
        """Remove all netem/tbf rules and return to baseline."""
        result = self._run(["tc", "qdisc", "del", "dev", self.iface, "root"])

        harmless_errors = [
            "Cannot delete qdisc with handle of zero",
            "No such file or directory",
            "Invalid argument",
            "Cannot find device",
        ]

        if result["returncode"] != 0:
            stderr = result.get("stderr", "")
            if any(msg in stderr for msg in harmless_errors):
                result["returncode"] = 0
                result["note"] = "clear skipped: no existing qdisc"
                return result

        return result

    def apply(
        self,
        delay_ms: int = 0,
        jitter_ms: int = 0,
        loss_pct: float = 0,
        bandwidth_kbit: int = None,
    ):
        """ใส่ network impairment ตาม scenario (egress ของ self.iface เท่านั้น)"""

        clear_result = self.clear()

        has_bandwidth = bandwidth_kbit is not None and bandwidth_kbit > 0

        if delay_ms == 0 and jitter_ms == 0 and loss_pct == 0 and not has_bandwidth:
            return {
                "returncode": 0,
                "stdout": "baseline (no impairment)",
                "stderr": "",
                "cmd": "baseline",
                "clear_before_apply": clear_result,
            }

        netem_cmd = [
            "tc", "qdisc", "add",
            "dev", self.iface,
            "root",
            "handle", "1:",
            "netem",
        ]

        if delay_ms > 0:
            netem_cmd += ["delay", f"{delay_ms}ms"]

            if jitter_ms > 0:
                netem_cmd += [f"{jitter_ms}ms"]

        elif jitter_ms > 0:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": "jitter_ms > 0 requires delay_ms > 0",
                "cmd": " ".join(netem_cmd),
                "clear_before_apply": clear_result,
            }

        if loss_pct > 0:
            netem_cmd += ["loss", f"{loss_pct}%"]

        netem_result = self._run(netem_cmd)
        netem_result["clear_before_apply"] = clear_result

        tbf_result = None

        if has_bandwidth:
            tbf_cmd = [
                "tc", "qdisc", "add",
                "dev", self.iface,
                "parent", "1:",
                "handle", "10:",
                "tbf",
                "rate", f"{bandwidth_kbit}kbit",
                "burst", "32kbit",
                "latency", "400ms",
            ]

            tbf_result = self._run(tbf_cmd)

        netem_result["tbf"] = tbf_result
        return netem_result

    def current_status(self):
        result = self._run(["tc", "qdisc", "show", "dev", self.iface])
        return result["stdout"].strip()
