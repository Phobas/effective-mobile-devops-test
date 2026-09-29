from pathlib import Path
import re

p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()


def sub1(text, pattern, repl, label, flags=0):
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise SystemExit(f"{label}: expected one replacement, got {n}")
    return out


# ---------------------------------------------------------------------------
# 1. Use the complete Linux HCI -> MGMT status mapping relevant to Bluetooth
#    2.x-5.x controllers.  The earlier compatibility bridge had a deliberately
#    small table; notably HCI PIN/Key Missing (0x06) was incorrectly exposed as
#    MGMT_NOT_PAIRED instead of MGMT_AUTH_FAILED and OE Low Resources (0x14)
#    was treated as DISCONNECTED instead of NO_RESOURCES.
# ---------------------------------------------------------------------------
new_status = r'''static u8 compat_hci_status(u8 status)
{
        switch (status) {
        case 0x00: return 0x00; /* SUCCESS */
        case 0x01: return 0x01; /* UNKNOWN_COMMAND */
        case 0x02: return 0x02; /* NOT_CONNECTED */
        case 0x03: return 0x03; /* FAILED */
        case 0x04: return 0x04; /* CONNECT_FAILED */
        case 0x05: return 0x05; /* AUTH_FAILED */
        case 0x06: return 0x05; /* PIN_OR_KEY_MISSING -> AUTH_FAILED */
        case 0x07: return 0x07; /* NO_RESOURCES */
        case 0x08: return 0x08; /* TIMEOUT */
        case 0x09: return 0x07; /* MAX_CONNECTIONS -> NO_RESOURCES */
        case 0x0a: return 0x07; /* MAX_SCO -> NO_RESOURCES */
        case 0x0b: return 0x09; /* ALREADY_CONNECTED */
        case 0x0c: return 0x0a; /* BUSY */
        case 0x0d: return 0x07; /* REJECTED_LIMITED_RESOURCES */
        case 0x0e: return 0x0b; /* REJECTED_SECURITY */
        case 0x0f: return 0x0b; /* REJECTED_PERSONAL */
        case 0x10: return 0x08; /* HOST_TIMEOUT */
        case 0x11: return 0x0c; /* NOT_SUPPORTED */
        case 0x12: return 0x0d; /* INVALID_PARAMS */
        case 0x13: return 0x0e; /* REMOTE_USER_TERM */
        case 0x14: return 0x07; /* REMOTE_LOW_RESOURCES */
        case 0x15: return 0x0e; /* REMOTE_POWER_OFF */
        case 0x16: return 0x0e; /* LOCAL_HOST_TERM */
        case 0x17: return 0x0a; /* REPEATED_ATTEMPTS */
        case 0x18: return 0x0b; /* PAIRING_NOT_ALLOWED */
        case 0x19: return 0x03; /* UNKNOWN_LMP_PDU */
        case 0x1a: return 0x0c; /* UNSUPPORTED_REMOTE_FEATURE */
        case 0x1b: return 0x0b; /* SCO_OFFSET_REJECTED */
        case 0x1c: return 0x0b; /* SCO_INTERVAL_REJECTED */
        case 0x1d: return 0x0b; /* SCO_AIR_MODE_REJECTED */
        case 0x1e: return 0x0d; /* INVALID_LMP_PARAMS */
        case 0x1f: return 0x03; /* UNSPECIFIED_ERROR */
        case 0x20: return 0x0c; /* UNSUPPORTED_LMP_PARAM */
        case 0x21: return 0x03; /* ROLE_CHANGE_NOT_ALLOWED */
        case 0x22: return 0x08; /* LMP_RESPONSE_TIMEOUT */
        case 0x23: return 0x03; /* LMP_TRANSACTION_COLLISION */
        case 0x24: return 0x03; /* LMP_PDU_NOT_ALLOWED */
        case 0x25: return 0x0b; /* ENCRYPTION_MODE_NOT_ACCEPTED */
        case 0x26: return 0x03; /* UNIT_LINK_KEY_USED */
        case 0x27: return 0x0c; /* QOS_NOT_SUPPORTED */
        case 0x28: return 0x08; /* INSTANT_PASSED */
        case 0x29: return 0x0c; /* PAIRING_NOT_SUPPORTED */
        case 0x2a: return 0x03; /* TRANSACTION_COLLISION */
        case 0x2b: return 0x03; /* RESERVED */
        case 0x2c: return 0x0d; /* UNACCEPTABLE_PARAMETER */
        case 0x2d: return 0x0b; /* QOS_REJECTED */
        case 0x2e: return 0x0c; /* CLASSIFICATION_NOT_SUPPORTED */
        case 0x2f: return 0x0b; /* INSUFFICIENT_SECURITY */
        case 0x30: return 0x0d; /* PARAMETER_OUT_OF_RANGE */
        case 0x31: return 0x03; /* RESERVED */
        case 0x32: return 0x0a; /* ROLE_SWITCH_PENDING */
        case 0x33: return 0x03; /* RESERVED */
        case 0x34: return 0x03; /* SLOT_VIOLATION */
        case 0x35: return 0x03; /* ROLE_SWITCH_FAILED */
        case 0x36: return 0x0d; /* EIR_TOO_LARGE */
        case 0x37: return 0x0c; /* SIMPLE_PAIRING_NOT_SUPPORTED */
        case 0x38: return 0x0a; /* HOST_BUSY_PAIRING */
        case 0x39: return 0x0b; /* NO_SUITABLE_CHANNEL */
        case 0x3a: return 0x0a; /* CONTROLLER_BUSY */
        case 0x3b: return 0x0d; /* UNSUITABLE_CONNECTION_INTERVAL */
        case 0x3c: return 0x08; /* DIRECTED_ADVERTISING_TIMEOUT */
        case 0x3d: return 0x05; /* MIC_FAILURE -> AUTH_FAILED */
        case 0x3e: return 0x04; /* CONNECTION_ESTABLISHMENT_FAILED */
        case 0x3f: return 0x04; /* MAC_CONNECTION_FAILED */
        default:   return 0x03; /* FAILED */
        }
}'''

s = sub1(
    s,
    r"static u8 compat_hci_status\(u8 status\)\n\{.*?\n\}\n\nstatic u8 compat_errno_status",
    new_status + "\n\nstatic u8 compat_errno_status",
    "complete HCI status mapping",
    re.S,
)

# ---------------------------------------------------------------------------
# 2. Make Pair Device completion use the same canonical status mapping instead
#    of a second partial conversion table.
# ---------------------------------------------------------------------------
pair_start = s.find("static void pairing_complete(struct pending_cmd *cmd, u8 status)")
if pair_start < 0:
    raise SystemExit("pairing_complete: start not found")
pair_end = s.find("\n\nstatic void pairing_complete_cb", pair_start)
if pair_end < 0:
    raise SystemExit("pairing_complete: end not found")
seg = s[pair_start:pair_end]
seg, n = re.subn(
    r"\n\s*/\* Translate the common HCI outcomes needed by BlueZ\. \*/.*?\n\s*memset\(&ev, 0, sizeof\(ev\)\);",
    "\n        mgmt_status = compat_hci_status(status);\n\n        memset(&ev, 0, sizeof(ev));",
    seg,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit("pairing_complete: legacy status mapper not found")
s = s[:pair_start] + seg + s[pair_end:]

# ---------------------------------------------------------------------------
# 3. Validate BR/EDR Pair Device IO capability exactly like modern MGMT.
#    Valid classic/SSP values are 0x00..0x04.
# ---------------------------------------------------------------------------
needle = '''\tif (cp->addr_type != 0x00)\n\t\treturn cmd_status(sk, index, MGMT_OP_PAIR_DEVICE, EOPNOTSUPP);'''
repl = needle + '''\n\n\tif (cp->io_cap > 0x04)\n\t\treturn cmd_status(sk, index, MGMT_OP_PAIR_DEVICE, EINVAL);'''
if needle not in s:
    raise SystemExit("PAIR_DEVICE addr_type validation anchor not found")
s = s.replace(needle, repl, 1)

# ---------------------------------------------------------------------------
# 4. Reject invalid six-digit passkeys before they reach the controller.
# ---------------------------------------------------------------------------
needle = '''                passkey = cp->passkey;\n        }\n        if (addr_type != 0x00)'''
repl = '''                passkey = cp->passkey;\n                if (le32_to_cpu(passkey) > 999999)\n                        return cmd_status(sk, index, MGMT_OP_USER_PASSKEY_REPLY, EINVAL);\n        }\n        if (addr_type != 0x00)'''
if needle not in s:
    raise SystemExit("passkey validation anchor not found")
s = s.replace(needle, repl, 1)

# ---------------------------------------------------------------------------
# 5. CANCEL_PAIR_DEVICE is intentionally not advertised by this compatibility
#    layer yet.  The old 3.4 pending-command list is not race-safe against
#    pairing completion/cancellation; modern kernels needed dedicated fixes for
#    that race.  Failing the build if it becomes advertised prevents exposing
#    an unsafe half-implementation by accident.
# ---------------------------------------------------------------------------
read_start = s.find("static int compat_read_commands(")
if read_start < 0:
    raise SystemExit("compat_read_commands not found")
read_end = s.find("\n}\n", read_start)
if read_end < 0:
    raise SystemExit("compat_read_commands end not found")
read_seg = s[read_start:read_end]
if "MGMT_OP_CANCEL_PAIR_DEVICE" in read_seg or "0x001A" in read_seg or "0x001a" in read_seg:
    raise SystemExit("unsafe CANCEL_PAIR_DEVICE is advertised; remove it until race-safe cancellation exists")

# ---------------------------------------------------------------------------
# 6. Build-time invariants: these are the paths BlueZ 5.66 needs for the
#    BR/EDR Razer test.  Abort the build instead of silently shipping a kernel
#    with an accidentally regressed opcode/event bridge.
# ---------------------------------------------------------------------------
required_mgmt = [
    "compat_read_commands",
    "compat_hci_status",
    "compat_errno_status",
    "compat_user_passkey_reply",
    "MGMT_OP_PAIR_DEVICE",
    "MGMT_OP_USER_CONFIRM_REPLY",
    "MGMT_OP_USER_PASSKEY_REPLY",
    "MGMT_OP_USER_PASSKEY_NEG_REPLY",
    "MGMT_EV_USER_CONFIRM_REQUEST",
    "MGMT_EV_USER_PASSKEY_REQUEST",
    "MGMT_EV_AUTH_FAILED",
]
for token in required_mgmt:
    if token not in s:
        raise SystemExit("required MGMT v1 token missing: " + token)

p.write_text(s)
print("MGMT v1 hardening applied: canonical statuses, pair/passkey validation, safety audit")
