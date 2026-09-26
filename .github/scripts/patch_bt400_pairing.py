from pathlib import Path


def must_replace(text, old, new, label, count=1):
    if old not in text:
        raise SystemExit(f"{label}: anchor not found")
    return text.replace(old, new, count)


# Bridge BlueZ 5.66 Pair Device (0x0019, addr+type+io_cap) to the
# legacy flo pairing engine, which used 0x0014 and had no address-type byte.
h = Path("kernel/include/net/bluetooth/mgmt.h")
s = h.read_text()

s = must_replace(s,
    "#define MGMT_OP_PAIR_DEVICE\t\t0x0014",
    "#define MGMT_OP_PAIR_DEVICE\t\t0x0019",
    "PAIR_DEVICE opcode")

# Old 0x0019 collides with modern PAIR_DEVICE; move the legacy OOB command away.
s = must_replace(s,
    "#define MGMT_OP_ADD_REMOTE_OOB_DATA\t0x0019",
    "#define MGMT_OP_ADD_REMOTE_OOB_DATA\t0xE119",
    "ADD_REMOTE_OOB_DATA collision")

old = '''struct mgmt_cp_pair_device {\n\tbdaddr_t bdaddr;\n\t__u8 io_cap;\n} __packed;\nstruct mgmt_rp_pair_device {\n\tbdaddr_t bdaddr;\n\t__u8 status;\n} __packed;'''
new = '''struct mgmt_cp_pair_device {\n\tbdaddr_t bdaddr;\n\t__u8 addr_type;\n\t__u8 io_cap;\n} __packed;\nstruct mgmt_rp_pair_device {\n\tbdaddr_t bdaddr;\n\t__u8 addr_type;\n} __packed;'''
s = must_replace(s, old, new, "PAIR_DEVICE wire structs")
h.write_text(s)


p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()

# Replace legacy pairing completion with a modern MGMT Command Complete packet:
# opcode + status + {address,address_type}.  The generic cmd_complete helper was
# already modernized by the previous patch but always emits status=0, so pairing
# needs its own completion path to report authentication/connect failures.
a = s.index("static void pairing_complete(struct pending_cmd *cmd, u8 status)")
b = s.index("\n\nstatic void pairing_complete_cb", a)
new_pairing_complete = r'''static void pairing_complete(struct pending_cmd *cmd, u8 status)
{
        struct compat_pair_complete {
                __le16 opcode;
                __u8 status;
                bdaddr_t bdaddr;
                __u8 addr_type;
        } __packed ev;
        struct hci_conn *conn = cmd->user_data;
        __u8 mgmt_status;

        /* Translate the common HCI outcomes needed by BlueZ. */
        if (!status)
                mgmt_status = 0x00;
        else if (status == 0x05 || status == 0x06 || status == 0x17 ||
                 status == 0x18 || status == 0x23)
                mgmt_status = 0x05; /* Authentication Failed */
        else if (status == 0x08)
                mgmt_status = 0x08; /* Timeout */
        else if (status == 0x04)
                mgmt_status = 0x04; /* Connect Failed */
        else
                mgmt_status = 0x03; /* Failed */

        memset(&ev, 0, sizeof(ev));
        put_unaligned_le16(MGMT_OP_PAIR_DEVICE, &ev.opcode);
        ev.status = mgmt_status;
        bacpy(&ev.bdaddr, &conn->dst);
        ev.addr_type = 0x00; /* legacy flo pairing path is BR/EDR */

        mgmt_event(MGMT_EV_CMD_COMPLETE, cmd->index, &ev, sizeof(ev), cmd->sk);

        /* So we don't get further callbacks for this connection. */
        conn->connect_cfm_cb = NULL;
        conn->security_cfm_cb = NULL;
        conn->disconn_cfm_cb = NULL;

        hci_conn_put(conn);
        mgmt_pending_remove(cmd);
}
'''
s = s[:a] + new_pairing_complete + s[b:]

# BlueZ 5.66 includes address type in the Pair Device command.  The legacy
# engine can pair BR/EDR devices such as the Razer headset, but it cannot safely
# reinterpret LE address types here.  Reject LE explicitly instead of sending a
# classic ACL connection to the wrong transport.
needle = "\tcp = (void *) data;\n\n\tif (len != sizeof(*cp))\n\t\treturn cmd_status(sk, index, MGMT_OP_PAIR_DEVICE, EINVAL);"
repl = "\tcp = (void *) data;\n\n\tif (len != sizeof(*cp))\n\t\treturn cmd_status(sk, index, MGMT_OP_PAIR_DEVICE, EINVAL);\n\n\tif (cp->addr_type != 0x00)\n\t\treturn cmd_status(sk, index, MGMT_OP_PAIR_DEVICE, EOPNOTSUPP);"
s = must_replace(s, needle, repl, "PAIR_DEVICE length/type validation")

p.write_text(s)
print("BlueZ 5.66 BR/EDR pairing bridge patched")
