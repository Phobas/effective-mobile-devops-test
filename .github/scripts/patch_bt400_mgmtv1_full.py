from pathlib import Path
import re


def sub1(text, pattern, repl, label, flags=0):
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise SystemExit(f"{label}: expected one replacement, got {n}")
    return out


def set_define(text, name, value):
    pattern = rf"(#define\s+{re.escape(name)}\s+)0x[0-9A-Fa-f]+"
    out, n = re.subn(pattern, rf"\g<1>{value}", text, count=1)
    if n != 1:
        raise SystemExit(f"define {name}: expected one match, got {n}")
    return out


def replace_func(text, start_marker, end_marker, new_text, label):
    a = text.find(start_marker)
    if a < 0:
        raise SystemExit(f"{label}: start marker not found")
    b = text.find(end_marker, a)
    if b < 0:
        raise SystemExit(f"{label}: end marker not found")
    return text[:a] + new_text.rstrip() + "\n\n" + text[b:]


# ---------------------------------------------------------------------------
# Header: move the legacy flo command numbers onto the MGMT v1 numbers used
# by BlueZ 5.66.  Vendor-era commands that collide with standard MGMT v1 are
# moved into the private 0xExxx range rather than being accidentally invoked.
# ---------------------------------------------------------------------------
h = Path("kernel/include/net/bluetooth/mgmt.h")
s = h.read_text()

if "struct mgmt_addr_info" not in s:
    anchor = "struct mgmt_hdr {\n\t__le16 opcode;\n\t__le16 index;\n\t__le16 len;\n} __packed;\n"
    add = anchor + "\nstruct mgmt_addr_info {\n\tbdaddr_t bdaddr;\n\t__u8 type;\n} __packed;\n"
    if anchor not in s:
        raise SystemExit("mgmt_addr_info anchor not found")
    s = s.replace(anchor, add, 1)

if "#define MGMT_OP_READ_COMMANDS" not in s:
    s = s.replace("#define MGMT_OP_READ_VERSION\t\t0x0001\n",
                  "#define MGMT_OP_READ_VERSION\t\t0x0001\n#define MGMT_OP_READ_COMMANDS\t\t0x0002\n", 1)

remap = {
    "MGMT_OP_SET_PAIRABLE": "0x0009",
    "MGMT_OP_ADD_UUID": "0x0010",
    "MGMT_OP_REMOVE_UUID": "0x0011",
    "MGMT_OP_SET_DEV_CLASS": "0x000E",
    "MGMT_OP_SET_SERVICE_CACHE": "0xE00C",
    "MGMT_OP_LOAD_KEYS": "0x0012",
    "MGMT_OP_REMOVE_KEY": "0x001B",      # modern UNPAIR_DEVICE
    "MGMT_OP_DISCONNECT": "0x0014",
    "MGMT_OP_GET_CONNECTIONS": "0x0015",
    "MGMT_OP_PIN_CODE_REPLY": "0x0016",
    "MGMT_OP_PIN_CODE_NEG_REPLY": "0x0017",
    "MGMT_OP_SET_IO_CAPABILITY": "0x0018",
    "MGMT_OP_PAIR_DEVICE": "0x0019",
    "MGMT_OP_USER_CONFIRM_REPLY": "0x001C",
    "MGMT_OP_USER_CONFIRM_NEG_REPLY": "0x001D",
    "MGMT_OP_SET_LOCAL_NAME": "0x000F",
    # Do not expose the old P-192-only OOB implementation as modern 5.66 OOB.
    "MGMT_OP_READ_LOCAL_OOB_DATA": "0xE118",
    "MGMT_OP_ADD_REMOTE_OOB_DATA": "0xE119",
    "MGMT_OP_REMOVE_REMOTE_OOB_DATA": "0xE11A",
    "MGMT_OP_START_DISCOVERY": "0x0023",
    "MGMT_OP_STOP_DISCOVERY": "0x0024",
    "MGMT_OP_USER_PASSKEY_REPLY": "0x001E",
    "MGMT_OP_RESOLVE_NAME": "0xE11E",
    "MGMT_OP_SET_LIMIT_DISCOVERABLE": "0xE11F",
    "MGMT_OP_SET_CONNECTION_PARAMS": "0xE120",
    "MGMT_OP_ENCRYPT_LINK": "0xE121",
    "MGMT_OP_SET_RSSI_REPORTER": "0xE122",
    "MGMT_OP_UNSET_RSSI_REPORTER": "0xE123",
    "MGMT_OP_CANCEL_RESOLVE_NAME": "0xE124",
}
for name, value in remap.items():
    s = set_define(s, name, value)

if "#define MGMT_OP_CANCEL_PAIR_DEVICE" not in s:
    needle = "#define MGMT_OP_PAIR_DEVICE\t\t0x0019"
    pos = s.find(needle)
    if pos < 0:
        raise SystemExit("PAIR_DEVICE define not found")
    # Insert after the pair response structure instead of inside it.
    marker = "struct mgmt_rp_pair_device {\n\tbdaddr_t bdaddr;\n\t__u8 addr_type;\n} __packed;"
    if marker not in s:
        raise SystemExit("PAIR_DEVICE response marker not found")
    s = s.replace(marker, marker + "\n\n#define MGMT_OP_CANCEL_PAIR_DEVICE\t0x001A", 1)

if "#define MGMT_OP_USER_PASSKEY_NEG_REPLY" not in s:
    marker = "struct mgmt_cp_user_passkey_reply {"
    pos = s.find(marker)
    if pos < 0:
        raise SystemExit("passkey reply struct not found")
    end = s.find("} __packed;", pos)
    end += len("} __packed;")
    s = s[:end] + "\n\n#define MGMT_OP_USER_PASSKEY_NEG_REPLY\t0x001F\nstruct mgmt_cp_user_passkey_neg_reply {\n\tbdaddr_t bdaddr;\n\t__u8 addr_type;\n} __packed;" + s[end:]

# Modern wire structures, kept flat so the old implementation can continue to
# use cp->bdaddr with minimal code churn.
s = sub1(s, r"struct mgmt_cp_remove_key \{.*?\} __packed;",
'''struct mgmt_cp_remove_key {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 disconnect;
} __packed;''', "unpair struct", re.S)

s = sub1(s, r"struct mgmt_cp_disconnect \{.*?struct mgmt_rp_disconnect \{.*?\} __packed;",
'''struct mgmt_cp_disconnect {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
} __packed;
struct mgmt_rp_disconnect {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
} __packed;''', "disconnect structs", re.S)

s = sub1(s, r"struct mgmt_rp_get_connections \{.*?\} __packed;",
'''struct mgmt_rp_get_connections {
\t__le16 conn_count;
\tstruct mgmt_addr_info conn[0];
} __packed;''', "get connections struct", re.S)

s = sub1(s, r"struct mgmt_cp_pin_code_reply \{.*?struct mgmt_rp_pin_code_reply \{.*?\} __packed;",
'''struct mgmt_cp_pin_code_reply {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 pin_len;
\t__u8 pin_code[16];
} __packed;
struct mgmt_rp_pin_code_reply {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
} __packed;''', "pin reply structs", re.S)

s = sub1(s, r"struct mgmt_cp_pin_code_neg_reply \{.*?\} __packed;",
'''struct mgmt_cp_pin_code_neg_reply {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
} __packed;''', "pin neg struct", re.S)

s = sub1(s, r"struct mgmt_cp_user_confirm_reply \{.*?struct mgmt_rp_user_confirm_reply \{.*?\} __packed;",
'''struct mgmt_cp_user_confirm_reply {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
} __packed;
struct mgmt_rp_user_confirm_reply {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
} __packed;''', "confirm structs", re.S)

s = sub1(s, r"struct mgmt_cp_set_local_name \{.*?\} __packed;",
'''struct mgmt_cp_set_local_name {
\t__u8 name[MGMT_MAX_NAME_LENGTH];
\t__u8 short_name[11];
} __packed;''', "local name struct", re.S)

s = sub1(s, r"struct mgmt_cp_user_passkey_reply \{.*?\} __packed;",
'''struct mgmt_cp_user_passkey_reply {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__le32 passkey;
} __packed;''', "passkey reply struct", re.S)

# Event ABI: keep legacy-only notifications out of standard MGMT v1 event
# numbers and modernize the events BlueZ actually consumes.
event_remap = {
    "MGMT_EV_POWERED": "0xE006",
    "MGMT_EV_DISCOVERABLE": "0xE007",
    "MGMT_EV_CONNECTABLE": "0xE008",
    "MGMT_EV_PAIRABLE": "0xE009",
    "MGMT_EV_NEW_KEY": "0x0009",
    "MGMT_EV_LOCAL_NAME_CHANGED": "0x0008",
    "MGMT_EV_USER_PASSKEY_REQUEST": "0x0010",
    "MGMT_EV_AUTH_FAILED": "0x0011",
    "MGMT_EV_REMOTE_NAME": "0xE113",
    "MGMT_EV_DISCOVERING": "0xE114",
    "MGMT_EV_ENCRYPT_CHANGE": "0xE116",
    "MGMT_EV_REMOTE_CLASS": "0xE117",
    "MGMT_EV_REMOTE_VERSION": "0xE118",
    "MGMT_EV_REMOTE_FEATURES": "0xE119",
    "MGMT_EV_RSSI_UPDATE": "0xE120",
}
for name, value in event_remap.items():
    s = set_define(s, name, value)

if "#define MGMT_EV_NEW_SETTINGS" not in s:
    s = s.replace("#define MGMT_EV_INDEX_REMOVED\t\t0x0005\n",
                  "#define MGMT_EV_INDEX_REMOVED\t\t0x0005\n\n#define MGMT_EV_NEW_SETTINGS\t\t0x0006\n", 1)

if "struct mgmt_link_key_info" not in s:
    marker = "#define MGMT_EV_NEW_KEY\t\t\t0x0009\n"
    block = '''struct mgmt_link_key_info {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 key_type;
\t__u8 val[16];
\t__u8 pin_len;
} __packed;

'''
    if marker not in s:
        raise SystemExit("new key marker not found")
    s = s.replace(marker, block + marker, 1)

s = sub1(s, r"struct mgmt_ev_new_key \{.*?\} __packed;",
'''struct mgmt_ev_new_key {
\t__u8 store_hint;
\tstruct mgmt_link_key_info key;
} __packed;''', "new link key event", re.S)

s = sub1(s, r"struct mgmt_ev_connected \{.*?\} __packed;",
'''struct mgmt_ev_connected {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__le32 flags;
\t__le16 eir_len;
\t__u8 eir[0];
} __packed;''', "connected event", re.S)

s = sub1(s, r"struct mgmt_ev_disconnected \{.*?\} __packed;",
'''struct mgmt_ev_disconnected {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 reason;
} __packed;''', "disconnected event", re.S)

s = sub1(s, r"struct mgmt_ev_connect_failed \{.*?\} __packed;",
'''struct mgmt_ev_connect_failed {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 status;
} __packed;''', "connect failed event", re.S)

s = sub1(s, r"struct mgmt_ev_pin_code_request \{.*?\} __packed;",
'''struct mgmt_ev_pin_code_request {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 secure;
} __packed;''', "pin request event", re.S)

s = sub1(s, r"struct mgmt_ev_user_confirm_request \{.*?\} __packed;",
'''struct mgmt_ev_user_confirm_request {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 confirm_hint;
\t__le32 value;
} __packed;''', "confirm request event", re.S)

s = sub1(s, r"struct mgmt_ev_auth_failed \{.*?\} __packed;",
'''struct mgmt_ev_auth_failed {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
\t__u8 status;
} __packed;''', "auth failed event", re.S)

s = sub1(s, r"struct mgmt_ev_local_name_changed \{.*?\} __packed;",
'''struct mgmt_ev_local_name_changed {
\t__u8 name[MGMT_MAX_NAME_LENGTH];
\t__u8 short_name[11];
} __packed;''', "local name event", re.S)

s = sub1(s, r"struct mgmt_ev_user_passkey_request \{.*?\} __packed;",
'''struct mgmt_ev_user_passkey_request {
\tbdaddr_t bdaddr;
\t__u8 addr_type;
} __packed;''', "passkey request event", re.S)

h.write_text(s)


# ---------------------------------------------------------------------------
# mgmt.c: MGMT v1 helpers and command/event bridges.
# ---------------------------------------------------------------------------
p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()

anchor = "LIST_HEAD(cmd_list);\n"
helper = r'''

/* BlueZ 5.66 / MGMT v1 compatibility helpers. */
static int mgmt_event(u16 event, u16 index, void *data, u16 data_len,
                                                struct sock *skip_sk);
static int cmd_complete(struct sock *sk, u16 index, u16 cmd, void *rp,
                                                size_t rp_len);

static u8 compat_hci_status(u8 status)
{
        switch (status) {
        case 0x00: return 0x00;
        case 0x01: return 0x01;
        case 0x02: return 0x02;
        case 0x04: return 0x04;
        case 0x05: return 0x05;
        case 0x06: return 0x06;
        case 0x07: return 0x07;
        case 0x08: return 0x08;
        case 0x09: case 0x0a: return 0x07;
        case 0x0b: return 0x09;
        case 0x0c: return 0x0a;
        case 0x0d: return 0x07;
        case 0x0e: case 0x0f: return 0x0b;
        case 0x10: return 0x08;
        case 0x11: return 0x0c;
        case 0x12: return 0x0d;
        case 0x13: case 0x14: case 0x15: case 0x16: return 0x0e;
        case 0x17: case 0x36: return 0x0a;
        case 0x18: return 0x0b;
        case 0x29: case 0x34: return 0x0c;
        case 0x3d: case 0x3e: return 0x04;
        default: return 0x03;
        }
}

static u8 compat_errno_status(u8 status)
{
        switch (status) {
        case EINVAL: return 0x0d;
        case ENODEV: return 0x11;
        case ENETDOWN: return 0x0f;
        case EBUSY: return 0x0a;
        case EALREADY: return 0x0a;
        case ENOMEM: return 0x07;
        case ENOTCONN: return 0x02;
        case EOPNOTSUPP: return 0x0c;
        case EACCES: return 0x14;
        case ETIMEDOUT: return 0x08;
        case ECANCELED: return 0x10;
        case EIO: return 0x03;
        default:
                return status <= 0x14 ? status : 0x03;
        }
}

static u32 compat_supported_settings(struct hci_dev *hdev)
{
        u32 settings = 0x00000001 | 0x00000002 | 0x00000008 |
                       0x00000010 | 0x00000080;
        if (hdev->ssp_mode > 0)
                settings |= 0x00000040;
        return settings;
}

static u32 compat_current_settings(struct hci_dev *hdev)
{
        u32 settings = 0x00000080;
        if (test_bit(HCI_UP, &hdev->flags))
                settings |= 0x00000001;
        if (test_bit(HCI_PSCAN, &hdev->flags))
                settings |= 0x00000002;
        if (test_bit(HCI_ISCAN, &hdev->flags))
                settings |= 0x00000008;
        if (test_bit(HCI_PAIRABLE, &hdev->flags))
                settings |= 0x00000010;
        if (hdev->ssp_mode > 0)
                settings |= 0x00000040;
        return settings;
}

static int compat_cmd_complete_status(struct sock *sk, u16 index, u16 opcode,
                                      u8 status, void *rp, size_t rp_len)
{
        struct sk_buff *skb;
        struct mgmt_hdr *hdr;
        struct mgmt_ev_cmd_complete *ev;

        skb = alloc_skb(sizeof(*hdr) + sizeof(*ev) + rp_len, GFP_ATOMIC);
        if (!skb)
                return -ENOMEM;
        hdr = (void *) skb_put(skb, sizeof(*hdr));
        hdr->opcode = cpu_to_le16(MGMT_EV_CMD_COMPLETE);
        hdr->index = cpu_to_le16(index);
        hdr->len = cpu_to_le16(sizeof(*ev) + rp_len);
        ev = (void *) skb_put(skb, sizeof(*ev) + rp_len);
        put_unaligned_le16(opcode, &ev->opcode);
        ev->status = status;
        if (rp && rp_len)
                memcpy(ev->data, rp, rp_len);
        if (sock_queue_rcv_skb(sk, skb) < 0)
                kfree_skb(skb);
        return 0;
}

static int compat_emit_new_settings(u16 index, struct sock *skip_sk)
{
        struct hci_dev *hdev;
        __le32 settings;
        int err;

        hdev = hci_dev_get(index);
        if (!hdev)
                return -ENODEV;
        settings = cpu_to_le32(compat_current_settings(hdev));
        err = mgmt_event(MGMT_EV_NEW_SETTINGS, index, &settings,
                         sizeof(settings), skip_sk);
        hci_dev_put(hdev);
        return err;
}

static int compat_read_commands(struct sock *sk)
{
        static const u16 commands[] = {
                MGMT_OP_READ_INDEX_LIST, MGMT_OP_READ_INFO,
                MGMT_OP_SET_POWERED, MGMT_OP_SET_DISCOVERABLE,
                MGMT_OP_SET_CONNECTABLE, MGMT_OP_SET_PAIRABLE,
                MGMT_OP_SET_DEV_CLASS, MGMT_OP_SET_LOCAL_NAME,
                MGMT_OP_ADD_UUID, MGMT_OP_REMOVE_UUID,
                MGMT_OP_LOAD_KEYS, MGMT_OP_DISCONNECT,
                MGMT_OP_GET_CONNECTIONS, MGMT_OP_PIN_CODE_REPLY,
                MGMT_OP_PIN_CODE_NEG_REPLY, MGMT_OP_SET_IO_CAPABILITY,
                MGMT_OP_PAIR_DEVICE, MGMT_OP_USER_CONFIRM_REPLY,
                MGMT_OP_USER_CONFIRM_NEG_REPLY, MGMT_OP_USER_PASSKEY_REPLY,
                MGMT_OP_USER_PASSKEY_NEG_REPLY,
                MGMT_OP_START_DISCOVERY, MGMT_OP_STOP_DISCOVERY,
        };
        static const u16 events[] = {
                0x0003, 0x0004, 0x0005, MGMT_EV_NEW_SETTINGS,
                MGMT_EV_LOCAL_NAME_CHANGED, MGMT_EV_NEW_KEY,
                MGMT_EV_CONNECTED, MGMT_EV_DISCONNECTED,
                MGMT_EV_CONNECT_FAILED, MGMT_EV_PIN_CODE_REQUEST,
                MGMT_EV_USER_CONFIRM_REQUEST, MGMT_EV_USER_PASSKEY_REQUEST,
                MGMT_EV_AUTH_FAILED, MGMT_EV_DEVICE_FOUND, 0x0013,
        };
        struct compat_read_commands_rp {
                __le16 num_commands;
                __le16 num_events;
                __le16 opcodes[0];
        } __packed *rp;
        size_t len = sizeof(*rp) + sizeof(commands) + sizeof(events);
        __le16 *dst;
        int i, err;

        rp = kzalloc(len, GFP_ATOMIC);
        if (!rp)
                return -ENOMEM;
        rp->num_commands = cpu_to_le16(ARRAY_SIZE(commands));
        rp->num_events = cpu_to_le16(ARRAY_SIZE(events));
        dst = rp->opcodes;
        for (i = 0; i < ARRAY_SIZE(commands); i++)
                put_unaligned_le16(commands[i], &dst[i]);
        dst += ARRAY_SIZE(commands);
        for (i = 0; i < ARRAY_SIZE(events); i++)
                put_unaligned_le16(events[i], &dst[i]);
        err = cmd_complete(sk, MGMT_INDEX_NONE, MGMT_OP_READ_COMMANDS,
                           rp, len);
        kfree(rp);
        return err;
}
'''
if "static u8 compat_hci_status" not in s:
    if anchor not in s:
        raise SystemExit("compat helper anchor not found")
    s = s.replace(anchor, anchor + helper, 1)

# Old code reports Linux errno values directly as MGMT status. Convert them.
needle = 'BT_DBG("sock %p, index %u, cmd %u, status %u", sk, index, cmd, status);\n'
if needle not in s:
    raise SystemExit("cmd_status debug anchor not found")
s = s.replace(needle, needle + '\n\tstatus = compat_errno_status(status);\n', 1)

# READ_INFO from the earlier patch now uses the same central settings helpers.
s = sub1(s,
    r"\t/\* Basic MGMT v1 settings only\. \*/\n\tsupported = .*?\n\tif \(test_bit\(HCI_ISCAN, &hdev->flags\)\)\n\t\tcurrent_settings \|= 0x00000008;",
    "\tsupported = compat_supported_settings(hdev);\n\tcurrent_settings = compat_current_settings(hdev);",
    "READ_INFO settings", re.S)

# Read Supported Commands (0x0002).
needle = "\tcase MGMT_OP_READ_VERSION:\n\t\terr = read_version(sk);\n\t\tbreak;\n\tcase MGMT_OP_READ_INDEX_LIST:"
repl = "\tcase MGMT_OP_READ_VERSION:\n\t\terr = read_version(sk);\n\t\tbreak;\n\tcase MGMT_OP_READ_COMMANDS:\n\t\terr = compat_read_commands(sk);\n\t\tbreak;\n\tcase MGMT_OP_READ_INDEX_LIST:"
if needle not in s:
    raise SystemExit("READ_COMMANDS dispatch anchor not found")
s = s.replace(needle, repl, 1)

# Restore handlers that the initial safety probe deliberately disabled. Their
# macros now point at the correct modern command numbers.
restore = [
    ('case MGMT_OP_REMOVE_KEY:\n\t\terr = cmd_status(sk, index, opcode, 0x01);',
     'case MGMT_OP_REMOVE_KEY:\n\t\terr = remove_key(sk, index, buf + sizeof(*hdr), len);'),
    ('case MGMT_OP_DISCONNECT:\n\t\terr = cmd_status(sk, index, opcode, 0x01);',
     'case MGMT_OP_DISCONNECT:\n\t\terr = disconnect(sk, index, buf + sizeof(*hdr), len);'),
    ('case MGMT_OP_GET_CONNECTIONS:\n\t\terr = cmd_status(sk, index, opcode, 0x01);',
     'case MGMT_OP_GET_CONNECTIONS:\n\t\terr = get_connections(sk, index);'),
    ('case MGMT_OP_PIN_CODE_REPLY:\n\t\terr = cmd_status(sk, index, opcode, 0x01);',
     'case MGMT_OP_PIN_CODE_REPLY:\n\t\terr = pin_code_reply(sk, index, buf + sizeof(*hdr), len);'),
    ('case MGMT_OP_PIN_CODE_NEG_REPLY:\n\t\terr = cmd_status(sk, index, opcode, 0x01);',
     'case MGMT_OP_PIN_CODE_NEG_REPLY:\n\t\terr = pin_code_neg_reply(sk, index, buf + sizeof(*hdr), len);'),
]
for old, new in restore:
    if old not in s:
        raise SystemExit("restore dispatcher anchor missing: " + old.splitlines()[0])
    s = s.replace(old, new, 1)

# Set Discoverable has a timeout field in MGMT v1. The legacy engine only needs
# the first byte; accept the full 3-byte payload and ignore timeout.
a = s.index("static int set_discoverable(")
b = s.index("static int set_connectable(", a)
seg = s[a:b]
seg, n = re.subn(r"if \(len != sizeof\(\*cp\)\)", "if (len != 3)", seg, count=1)
if n != 1:
    raise SystemExit("set_discoverable length check not found")
s = s[:a] + seg + s[b:]

# Modern mode-setting commands return Current_Settings (4 bytes), not a single
# mode byte.
a = s.index("static int send_mode_rsp(")
b = s.index("static int set_pairable(", a)
new_send_mode = r'''static int send_mode_rsp(struct sock *sk, u16 opcode, u16 index, u8 val)
{
        struct hci_dev *hdev;
        __le32 rp;

        (void) val;
        hdev = hci_dev_get(index);
        if (!hdev)
                return cmd_status(sk, index, opcode, ENODEV);
        rp = cpu_to_le32(compat_current_settings(hdev));
        hci_dev_put(hdev);
        return cmd_complete(sk, index, opcode, &rp, sizeof(rp));
}

'''
s = s[:a] + new_send_mode + s[b:]

# Convert legacy settings notifications into the single MGMT v1 NEW_SETTINGS
# event. These regexes intentionally cover line wrapping in the source.
settings_events = [
    (r"mgmt_event\(MGMT_EV_POWERED,\s*index,\s*&ev,\s*sizeof\(ev\),\s*match\.sk\)",
     "compat_emit_new_settings(index, match.sk)"),
    (r"mgmt_event\(MGMT_EV_DISCOVERABLE,\s*index,\s*&ev,\s*sizeof\(ev\),\s*match\.sk\)",
     "compat_emit_new_settings(index, match.sk)"),
    (r"mgmt_event\(MGMT_EV_CONNECTABLE,\s*index,\s*&ev,\s*sizeof\(ev\),\s*match\.sk\)",
     "compat_emit_new_settings(index, match.sk)"),
    (r"mgmt_event\(MGMT_EV_PAIRABLE,\s*index,\s*&ev,\s*sizeof\(ev\),\s*NULL\)",
     "compat_emit_new_settings(index, NULL)"),
]
for pat, repl in settings_events:
    s, n = re.subn(pat, repl, s, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("settings event bridge missing: " + pat)

# Modern LOAD_LINK_KEYS. This also sets HCI_LINK_KEYS, fixing the unanswered
# Link Key Request state without relying solely on the HCI fallback patch.
a = s.index("static int load_keys(")
b = s.index("static int __attribute__((unused)) remove_key(", a)
new_load_keys = r'''static int load_keys(struct sock *sk, u16 index, unsigned char *data, u16 len)
{
        struct compat_link_key {
                bdaddr_t bdaddr;
                __u8 addr_type;
                __u8 key_type;
                __u8 val[16];
                __u8 pin_len;
        } __packed;
        struct compat_load_keys {
                __u8 debug_keys;
                __le16 key_count;
                struct compat_link_key keys[0];
        } __packed *cp = (void *) data;
        struct hci_dev *hdev;
        u16 count, expected;
        int i, err = 0;

        if (len < sizeof(*cp))
                return cmd_status(sk, index, MGMT_OP_LOAD_KEYS, EINVAL);
        count = get_unaligned_le16(&cp->key_count);
        expected = sizeof(*cp) + count * sizeof(struct compat_link_key);
        if (len != expected || cp->debug_keys > 1)
                return cmd_status(sk, index, MGMT_OP_LOAD_KEYS, EINVAL);
        for (i = 0; i < count; i++)
                if (cp->keys[i].addr_type != 0x00)
                        return cmd_status(sk, index, MGMT_OP_LOAD_KEYS, EINVAL);

        hdev = hci_dev_get(index);
        if (!hdev)
                return cmd_status(sk, index, MGMT_OP_LOAD_KEYS, ENODEV);
        hci_dev_lock_bh(hdev);
        hci_link_keys_clear(hdev);
        set_bit(HCI_LINK_KEYS, &hdev->flags);
        if (cp->debug_keys)
                set_bit(HCI_DEBUG_KEYS, &hdev->flags);
        else
                clear_bit(HCI_DEBUG_KEYS, &hdev->flags);
        for (i = 0; i < count; i++) {
                struct compat_link_key *key = &cp->keys[i];
                hci_add_link_key(hdev, 0, &key->bdaddr, key->val,
                                 key->key_type, key->pin_len);
        }
        hci_dev_unlock_bh(hdev);
        hci_dev_put(hdev);
        err = cmd_complete(sk, index, MGMT_OP_LOAD_KEYS, NULL, 0);
        return err;
}

'''
s = s[:a] + new_load_keys + s[b:]

# GET_CONNECTIONS now returns {address,type} entries.
a = s.index("static int __attribute__((unused)) get_connections(")
b = s.index("static int __attribute__((unused)) pin_code_reply(", a)
new_get_connections = r'''static int __attribute__((unused)) get_connections(struct sock *sk, u16 index)
{
        struct compat_rp {
                __le16 conn_count;
                struct mgmt_addr_info addr[0];
        } __packed *rp;
        struct hci_dev *hdev;
        struct list_head *pos;
        size_t len;
        u16 count = 0, i = 0;
        int err;

        hdev = hci_dev_get(index);
        if (!hdev)
                return cmd_status(sk, index, MGMT_OP_GET_CONNECTIONS, ENODEV);
        hci_dev_lock_bh(hdev);
        list_for_each(pos, &hdev->conn_hash.list)
                count++;
        len = sizeof(*rp) + count * sizeof(struct mgmt_addr_info);
        rp = kzalloc(len, GFP_ATOMIC);
        if (!rp) {
                hci_dev_unlock_bh(hdev);
                hci_dev_put(hdev);
                return -ENOMEM;
        }
        put_unaligned_le16(count, &rp->conn_count);
        list_for_each(pos, &hdev->conn_hash.list) {
                struct hci_conn *c = list_entry(pos, struct hci_conn, list);
                bacpy(&rp->addr[i].bdaddr, &c->dst);
                rp->addr[i].type = (c->type == LE_LINK) ? 0x01 : 0x00;
                i++;
        }
        hci_dev_unlock_bh(hdev);
        hci_dev_put(hdev);
        err = cmd_complete(sk, index, MGMT_OP_GET_CONNECTIONS, rp, len);
        kfree(rp);
        return err;
}

'''
s = s[:a] + new_get_connections + s[b:]

# Validate address type for classic PIN responses. Existing HCI command code can
# then keep using cp->bdaddr and pin fields.
for fname in ("pin_code_reply", "pin_code_neg_reply"):
    marker = f"static int __attribute__((unused)) {fname}("
    a = s.index(marker)
    # limit edit to next function
    b = s.find("\nstatic ", a + len(marker))
    seg = s[a:b]
    check = "\n\tif (cp->addr_type != 0x00)\n\t\treturn cmd_status(sk, index, " + ("MGMT_OP_PIN_CODE_REPLY" if fname == "pin_code_reply" else "MGMT_OP_PIN_CODE_NEG_REPLY") + ", EINVAL);\n"
    needle = "\tif (len != sizeof(*cp))\n\t\treturn cmd_status"
    pos = seg.find(needle)
    if pos < 0:
        raise SystemExit(fname + " length anchor not found")
    # insert after the two-line return statement using the next blank line
    q = seg.find("\n\n", pos)
    seg = seg[:q] + check + seg[q:]
    s = s[:a] + seg + s[b:]

# Disconnect response includes address type.
needle = "\tbacpy(&rp.bdaddr, &cp->bdaddr);\n\n\tcmd_complete(cmd->sk, cmd->index, MGMT_OP_DISCONNECT, &rp, sizeof(rp));"
repl = "\tbacpy(&rp.bdaddr, &cp->bdaddr);\n\trp.addr_type = cp->addr_type;\n\n\tcmd_complete(cmd->sk, cmd->index, MGMT_OP_DISCONNECT, &rp, sizeof(rp));"
if needle not in s:
    raise SystemExit("disconnect response anchor not found")
s = s.replace(needle, repl, 1)

# Pairing/user-interaction events in MGMT v1 wire format.
# Existing old logic computes auto_confirm; in MGMT v1 this is Confirm_Hint.
s = s.replace("ev.auto_confirm", "ev.confirm_hint")
s = s.replace("\tev.event = event;\n", "")
needle = "no_auto_confirm:\n\tbacpy(&ev.bdaddr, bdaddr);\n\tput_unaligned_le32(value, &ev.value);"
repl = "no_auto_confirm:\n\tbacpy(&ev.bdaddr, bdaddr);\n\tev.addr_type = 0x00;\n\tput_unaligned_le32(value, &ev.value);"
if needle not in s:
    raise SystemExit("user confirmation event anchor not found")
s = s.replace(needle, repl, 1)

# Passkey request and PIN request carry BR/EDR address type.
needle = "\tbacpy(&ev.bdaddr, bdaddr);\n\n\treturn mgmt_event(MGMT_EV_USER_PASSKEY_REQUEST"
repl = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.addr_type = 0x00;\n\n\treturn mgmt_event(MGMT_EV_USER_PASSKEY_REQUEST"
if needle not in s:
    raise SystemExit("passkey request event anchor not found")
s = s.replace(needle, repl, 1)

# The first matching bacpy in mgmt_pin_code_request is followed by ev.secure.
needle = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.secure = secure;"
repl = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.addr_type = 0x00;\n\tev.secure = secure;"
if needle not in s:
    raise SystemExit("pin request event anchor not found")
s = s.replace(needle, repl, 1)

# Authentication Failed: modern event number, address type and MGMT status.
needle = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.status = status;\n\n\treturn mgmt_event(MGMT_EV_AUTH_FAILED"
repl = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.addr_type = 0x00;\n\tev.status = compat_hci_status(status);\n\n\treturn mgmt_event(MGMT_EV_AUTH_FAILED"
if needle not in s:
    raise SystemExit("auth failed event anchor not found")
s = s.replace(needle, repl, 1)

# New Link Key: drop the vendor auth/dlen extension and emit the MGMT v1 event.
a = s.index("int mgmt_new_key(")
b = s.index("int mgmt_connected(", a)
new_new_key = r'''int mgmt_new_key(u16 index, struct link_key *key, u8 bonded)
{
        struct mgmt_ev_new_key ev;

        memset(&ev, 0, sizeof(ev));
        ev.store_hint = bonded;
        bacpy(&ev.key.bdaddr, &key->bdaddr);
        ev.key.addr_type = 0x00;
        ev.key.key_type = key->key_type;
        memcpy(ev.key.val, key->val, sizeof(ev.key.val));
        ev.key.pin_len = key->pin_len;
        return mgmt_event(MGMT_EV_NEW_KEY, index, &ev, sizeof(ev), NULL);
}

'''
s = s[:a] + new_new_key + s[b:]

# Connected event payload: address type + flags + EIR length.
a = s.index("int mgmt_connected(")
b = s.index("int mgmt_le_conn_params(", a)
new_connected = r'''int mgmt_connected(u16 index, bdaddr_t *bdaddr, u8 le)
{
        struct mgmt_ev_connected ev;
        struct pending_cmd *cmd;

        memset(&ev, 0, sizeof(ev));
        bacpy(&ev.bdaddr, bdaddr);
        ev.addr_type = le ? 0x01 : 0x00;
        put_unaligned_le32(0, &ev.flags);
        put_unaligned_le16(0, &ev.eir_len);

        cmd = mgmt_pending_find(MGMT_OP_LE_CREATE_CONN_WHITE_LIST, index);
        if (cmd)
                mgmt_pending_remove(cmd);
        return mgmt_event(MGMT_EV_CONNECTED, index, &ev, sizeof(ev), NULL);
}

'''
s = s[:a] + new_connected + s[b:]

# Disconnect/connect-failed event structures are otherwise compatible once the
# address type byte is populated. Translate HCI reason/status for BlueZ.
needle = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.reason = reason;"
repl = '''\tbacpy(&ev.bdaddr, bdaddr);
\tev.addr_type = 0x00;
\tif (reason == 0x08)
\t\tev.reason = 0x01;
\telse if (reason == 0x16)
\t\tev.reason = 0x02;
\telse if (reason == 0x13)
\t\tev.reason = 0x03;
\telse
\t\tev.reason = 0x00;'''
if needle not in s:
    raise SystemExit("disconnected event anchor not found")
s = s.replace(needle, repl, 1)

needle = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.status = status;\n\n\treturn mgmt_event(MGMT_EV_CONNECT_FAILED"
repl = "\tbacpy(&ev.bdaddr, bdaddr);\n\tev.addr_type = 0x00;\n\tev.status = compat_hci_status(status);\n\n\treturn mgmt_event(MGMT_EV_CONNECT_FAILED"
if needle not in s:
    raise SystemExit("connect failed event anchor not found")
s = s.replace(needle, repl, 1)

# Modern local-name event has a short-name field; zero-fill it.
needle = "\tmemset(&ev, 0, sizeof(ev));\n\tmemcpy(ev.name, name, HCI_MAX_NAME_LENGTH);"
if needle in s:
    # already safe because memset covers short_name after header struct upgrade
    pass
else:
    # Some vendor revisions don't memset first; inject it before copy.
    needle2 = "\tmemcpy(ev.name, name, HCI_MAX_NAME_LENGTH);"
    if needle2 in s:
        s = s.replace(needle2, "\tmemset(&ev, 0, sizeof(ev));\n" + needle2, 1)

# Confirmation replies now contain address type. Reject LE here because this
# compatibility path is intentionally BR/EDR; the old LE/SMP engine is separate.
a = s.index("static int user_confirm_reply(")
b = s.index("static int set_local_name(", a)
seg = s[a:b]
needle = "\tif (len < sizeof(*cp))\n\t\treturn cmd_status(sk, index, mgmt_op, EINVAL);"
if needle not in seg:
    raise SystemExit("confirm reply length anchor not found")
seg = seg.replace(needle, needle + "\n\n\tif (cp->addr_type != 0x00)\n\t\treturn cmd_status(sk, index, mgmt_op, EINVAL);", 1)
s = s[:a] + seg + s[b:]

# User Passkey Reply was incorrectly routed through USER_CONFIRM_REPLY in the
# vendor tree. Implement proper HCI passkey reply/negative reply and complete
# the MGMT command once queued.
insert_at = s.index("static int set_local_name(")
passkey_funcs = r'''static int compat_user_passkey_reply(struct sock *sk, u16 index,
                                      unsigned char *data, u16 len, int negative)
{
        struct hci_dev *hdev;
        int err;
        bdaddr_t *bdaddr;
        __u8 addr_type;
        __le32 passkey = 0;
        __u8 rp[7];

        if (negative) {
                struct mgmt_cp_user_passkey_neg_reply *cp = (void *) data;
                if (len != sizeof(*cp))
                        return cmd_status(sk, index, MGMT_OP_USER_PASSKEY_NEG_REPLY, EINVAL);
                bdaddr = &cp->bdaddr;
                addr_type = cp->addr_type;
        } else {
                struct mgmt_cp_user_passkey_reply *cp = (void *) data;
                if (len != sizeof(*cp))
                        return cmd_status(sk, index, MGMT_OP_USER_PASSKEY_REPLY, EINVAL);
                bdaddr = &cp->bdaddr;
                addr_type = cp->addr_type;
                passkey = cp->passkey;
        }
        if (addr_type != 0x00)
                return cmd_status(sk, index,
                        negative ? MGMT_OP_USER_PASSKEY_NEG_REPLY : MGMT_OP_USER_PASSKEY_REPLY,
                        EINVAL);
        hdev = hci_dev_get(index);
        if (!hdev)
                return cmd_status(sk, index,
                        negative ? MGMT_OP_USER_PASSKEY_NEG_REPLY : MGMT_OP_USER_PASSKEY_REPLY,
                        ENODEV);
        if (negative) {
                err = hci_send_cmd(hdev, HCI_OP_USER_PASSKEY_NEG_REPLY, 6, bdaddr);
        } else {
                struct hci_cp_user_passkey_reply cp;
                bacpy(&cp.bdaddr, bdaddr);
                cp.passkey = passkey;
                err = hci_send_cmd(hdev, HCI_OP_USER_PASSKEY_REPLY, sizeof(cp), &cp);
        }
        hci_dev_put(hdev);
        if (err < 0)
                return cmd_status(sk, index,
                        negative ? MGMT_OP_USER_PASSKEY_NEG_REPLY : MGMT_OP_USER_PASSKEY_REPLY,
                        -err);
        bacpy((bdaddr_t *)rp, bdaddr);
        rp[6] = 0x00;
        return compat_cmd_complete_status(sk, index,
                negative ? MGMT_OP_USER_PASSKEY_NEG_REPLY : MGMT_OP_USER_PASSKEY_REPLY,
                0x00, rp, sizeof(rp));
}

'''
s = s[:insert_at] + passkey_funcs + s[insert_at:]

# Separate passkey commands from the old confirmation dispatcher.
old = '''\tcase MGMT_OP_USER_CONFIRM_REPLY:
\tcase MGMT_OP_USER_PASSKEY_REPLY:
\tcase MGMT_OP_USER_CONFIRM_NEG_REPLY:
\t\terr = user_confirm_reply(sk, index, buf + sizeof(*hdr),
\t\t\t\t\t\t\t\tlen, opcode);
\t\tbreak;'''
new = '''\tcase MGMT_OP_USER_CONFIRM_REPLY:
\tcase MGMT_OP_USER_CONFIRM_NEG_REPLY:
\t\terr = user_confirm_reply(sk, index, buf + sizeof(*hdr),
\t\t\t\t\t\t\t\tlen, opcode);
\t\tbreak;
\tcase MGMT_OP_USER_PASSKEY_REPLY:
\t\terr = compat_user_passkey_reply(sk, index, buf + sizeof(*hdr), len, 0);
\t\tbreak;
\tcase MGMT_OP_USER_PASSKEY_NEG_REPLY:
\t\terr = compat_user_passkey_reply(sk, index, buf + sizeof(*hdr), len, 1);
\t\tbreak;'''
if old not in s:
    raise SystemExit("passkey dispatcher anchor not found")
s = s.replace(old, new, 1)

p.write_text(s)

print("Comprehensive BlueZ 5.66 MGMT v1 BR/EDR compatibility pass applied")
