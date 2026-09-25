from pathlib import Path


def must_replace(text, old, new, label, count=1):
    if old not in text:
        raise SystemExit(f"{label}: anchor not found")
    return text.replace(old, new, count)


# Move the legacy discovery opcodes to the values expected by BlueZ 5.66.
# The old 0x0023/0x0024 vendor-era commands are moved out of the way.
h = Path("kernel/include/net/bluetooth/mgmt.h")
s = h.read_text()
s = must_replace(s,
    "#define MGMT_OP_START_DISCOVERY\t\t0x001B",
    "#define MGMT_OP_START_DISCOVERY\t\t0x0023",
    "START_DISCOVERY opcode")
s = must_replace(s,
    "#define MGMT_OP_STOP_DISCOVERY\t\t0x001C",
    "#define MGMT_OP_STOP_DISCOVERY\t\t0x0024",
    "STOP_DISCOVERY opcode")
s = must_replace(s,
    "#define MGMT_OP_UNSET_RSSI_REPORTER\t\t0x0023",
    "#define MGMT_OP_UNSET_RSSI_REPORTER\t\t0xE123",
    "UNSET_RSSI_REPORTER collision")
s = must_replace(s,
    "#define MGMT_OP_CANCEL_RESOLVE_NAME\t0x0024",
    "#define MGMT_OP_CANCEL_RESOLVE_NAME\t0xE124",
    "CANCEL_RESOLVE_NAME collision")
h.write_text(s)


p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()

# Keep the one-byte modern discovery type supplied by BlueZ.  READ_INFO in the
# previous compatibility patch advertises this controller as BR/EDR capable,
# so BlueZ normally sends type 0x01.
anchor = "LIST_HEAD(cmd_list);\n"
compat = r'''

static __u8 compat_discovery_type = 0x01;

static int mgmt_event(u16 event, u16 index, void *data, u16 data_len,
                                                struct sock *skip_sk);

struct compat_mgmt_ev_discovering {
        __u8 type;
        __u8 discovering;
} __packed;

static int compat_mgmt_discovering(u16 index, __u8 discovering)
{
        struct compat_mgmt_ev_discovering ev;

        ev.type = compat_discovery_type;
        ev.discovering = discovering;

        /* MGMT_EV_DISCOVERING in BlueZ 5.66 */
        return mgmt_event(0x0013, index, &ev, sizeof(ev), NULL);
}
'''
if "static __u8 compat_discovery_type" not in s:
    s = must_replace(s, anchor, anchor + compat, "compat globals")

# The old DISCOVERING event is 0x0014 with a one-byte mgmt_mode payload.
# Replace every discovery-state emission with the modern 0x0013 {type,state}
# helper.  These are deliberately exact one-line replacements to avoid the
# overlapping substitutions that broke Run #18.
event_replacements = {
    "\tmgmt_event(MGMT_EV_DISCOVERING, cmd->index, &ev, sizeof(ev), NULL);":
        "\tcompat_mgmt_discovering(cmd->index, ev.val);",
    "\t\tmgmt_event(MGMT_EV_DISCOVERING, index, &cp, sizeof(cp), NULL);":
        "\t\tcompat_mgmt_discovering(index, cp.val);",
    "\tmgmt_event(MGMT_EV_DISCOVERING, index, &cp, sizeof(cp), NULL);":
        "\tcompat_mgmt_discovering(index, cp.val);",
    "\tmgmt_event(MGMT_EV_DISCOVERING, hdev->id, &cp, sizeof(cp), NULL);":
        "\tcompat_mgmt_discovering(hdev->id, cp.val);",
    "\tmgmt_event(MGMT_EV_DISCOVERING, index, &mode_cp, sizeof(mode_cp), NULL);":
        "\tcompat_mgmt_discovering(index, mode_cp.val);",
}
for old, new in event_replacements.items():
    if old in s:
        s = s.replace(old, new)

# BlueZ 5.66 expects successful START/STOP command-complete responses to carry
# the discovery type byte.  Replace the whole legacy response helper so there
# is no ambiguity around the wire layout.
a = s.index("static void discovery_rsp(struct pending_cmd *cmd, void *data)")
b = s.index("void mgmt_inquiry_started(u16 index)", a)
new_discovery_rsp = r'''static void discovery_rsp(struct pending_cmd *cmd, void *data)
{
        struct mgmt_mode ev;

        BT_DBG("");
        if (cmd->opcode == MGMT_OP_START_DISCOVERY) {
                ev.val = 1;
                cmd_complete(cmd->sk, cmd->index, MGMT_OP_START_DISCOVERY,
                             &compat_discovery_type,
                             sizeof(compat_discovery_type));
        } else {
                ev.val = 0;
                cmd_complete(cmd->sk, cmd->index, MGMT_OP_STOP_DISCOVERY,
                             &compat_discovery_type,
                             sizeof(compat_discovery_type));
                if (cmd->opcode == MGMT_OP_STOP_DISCOVERY) {
                        struct hci_dev *hdev = hci_dev_get(cmd->index);
                        if (hdev) {
                                del_timer(&hdev->disco_le_timer);
                                del_timer(&hdev->disco_timer);
                                hci_dev_put(hdev);
                        }
                }
        }

        compat_mgmt_discovering(cmd->index, ev.val);

        list_del(&cmd->list);
        mgmt_pending_free(cmd);
}

'''
s = s[:a] + new_discovery_rsp + s[b:]

# The immediate STOP completion path also needs the one-byte type response.
old = "\t\t\terr = cmd_complete(sk, index, MGMT_OP_STOP_DISCOVERY,\n\t\t\t\t\t\t\t\tNULL, 0);"
new = "\t\t\terr = cmd_complete(sk, index, MGMT_OP_STOP_DISCOVERY,\n\t\t\t\t\t\t&compat_discovery_type,\n\t\t\t\t\t\tsizeof(compat_discovery_type));"
if old in s:
    s = s.replace(old, new, 1)

# Parse the type byte before entering the legacy discovery engine.  The opcode
# macros above now resolve to modern 0x0023 and 0x0024.
old = "\tcase MGMT_OP_START_DISCOVERY:\n\t\terr = start_discovery(sk, index);\n\t\tbreak;"
new = "\tcase MGMT_OP_START_DISCOVERY:\n\t\tif (len != 1)\n\t\t\terr = cmd_status(sk, index, MGMT_OP_START_DISCOVERY, EINVAL);\n\t\telse {\n\t\t\tcompat_discovery_type = *(u8 *)(buf + sizeof(*hdr));\n\t\t\terr = start_discovery(sk, index);\n\t\t}\n\t\tbreak;"
s = must_replace(s, old, new, "START_DISCOVERY dispatch")

old = "\tcase MGMT_OP_STOP_DISCOVERY:\n\t\terr = stop_discovery(sk, index);\n\t\tbreak;"
new = "\tcase MGMT_OP_STOP_DISCOVERY:\n\t\tif (len != 1)\n\t\t\terr = cmd_status(sk, index, MGMT_OP_STOP_DISCOVERY, EINVAL);\n\t\telse {\n\t\t\tcompat_discovery_type = *(u8 *)(buf + sizeof(*hdr));\n\t\t\terr = stop_discovery(sk, index);\n\t\t}\n\t\tbreak;"
s = must_replace(s, old, new, "STOP_DISCOVERY dispatch")

# DEVICE_FOUND keeps event opcode 0x0012, but the old and modern payloads are
# unrelated.  Emit the BlueZ 5.66 variable-length layout while retaining the
# legacy scan-phase bookkeeping.
a = s.index("int mgmt_device_found(u16 index, bdaddr_t *bdaddr, u8 type, u8 le,")
b = s.index("\n\nint mgmt_remote_name(", a)
new_device_found = r'''int mgmt_device_found(u16 index, bdaddr_t *bdaddr, u8 type, u8 le,
                        u8 *dev_class, s8 rssi, u8 eir_len, u8 *eir)
{
        struct compat_addr_info {
                bdaddr_t bdaddr;
                __u8 type;
        } __packed;
        struct compat_device_found {
                struct compat_addr_info addr;
                __s8 rssi;
                __le32 flags;
                __le16 eir_len;
                __u8 eir[0];
        } __packed;
        __u8 event_buf[sizeof(struct compat_device_found) + HCI_MAX_EIR_LENGTH];
        struct compat_device_found *ev = (void *) event_buf;
        struct hci_dev *hdev;
        int err;

        BT_DBG("le: %d", le);
        (void) dev_class;

        if (eir_len > HCI_MAX_EIR_LENGTH)
                eir_len = HCI_MAX_EIR_LENGTH;

        memset(event_buf, 0, sizeof(event_buf));
        bacpy(&ev->addr.bdaddr, bdaddr);
        ev->addr.type = le ? (type ? 0x02 : 0x01) : 0x00;
        ev->rssi = rssi;
        put_unaligned_le32(0, &ev->flags);
        put_unaligned_le16(eir_len, &ev->eir_len);
        if (eir && eir_len)
                memcpy(ev->eir, eir, eir_len);

        err = mgmt_event(MGMT_EV_DEVICE_FOUND, index, ev,
                         sizeof(*ev) + eir_len, NULL);
        if (err < 0)
                return err;

        hdev = hci_dev_get(index);
        if (!hdev)
                return 0;

        if (hdev->disco_state == SCAN_IDLE)
                goto done;

        hdev->disco_int_count++;

        if (hdev->disco_int_count >= hdev->disco_int_phase) {
                struct hci_cp_inquiry cp = {{0x33, 0x8b, 0x9e}, 4, 0};
                struct hci_cp_le_set_scan_enable le_cp = {0, 0};

                hdev->disco_int_phase *= 2;
                hdev->disco_int_count = 0;
                if (hdev->disco_state == SCAN_LE) {
                        hci_send_cmd(hdev, HCI_OP_LE_SET_SCAN_ENABLE,
                                     sizeof(le_cp), &le_cp);
                        cp.num_rsp = (u8) hdev->disco_int_phase;
                        hci_send_cmd(hdev, HCI_OP_INQUIRY, sizeof(cp), &cp);
                        hdev->disco_state = SCAN_BR;
                        del_timer_sync(&hdev->disco_le_timer);
                }
        }

done:
        hci_dev_put(hdev);
        return 0;
}
'''
s = s[:a] + new_device_found + s[b:]

# Old REMOTE_NAME is event 0x0013, which BlueZ 5.66 interprets as DISCOVERING.
# Suppress the incompatible legacy event; DEVICE_FOUND is sufficient to expose
# the address during this compatibility stage.
a = s.index("int mgmt_remote_name(u16 index, bdaddr_t *bdaddr, u8 status, u8 *name)")
b = s.index("\n\nint mgmt_encrypt_change(", a)
new_remote_name = r'''int mgmt_remote_name(u16 index, bdaddr_t *bdaddr, u8 status, u8 *name)
{
        (void) index;
        (void) bdaddr;
        (void) status;
        (void) name;
        return 0;
}
'''
s = s[:a] + new_remote_name + s[b:]

# No legacy one-byte DISCOVERING event may remain in the generated source.
if "mgmt_event(MGMT_EV_DISCOVERING" in s:
    raise SystemExit("untranslated legacy DISCOVERING event remains")

p.write_text(s)

print("BlueZ 5.66 discovery bridge patched")
