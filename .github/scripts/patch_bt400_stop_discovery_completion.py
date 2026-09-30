from pathlib import Path

p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()

# BlueZ 5.66 requires the STOP_DISCOVERY terminal response to be delivered
# before DISCOVERING=0.  The legacy flo implementation does the opposite:
# it sets SCAN_IDLE, queues HCI Inquiry Cancel / LE Scan Disable, emits the
# state event immediately, and only later tears down its synthetic pending
# STOP command.  BlueZ therefore still has the D-Bus discovery client when it
# processes DISCOVERING=0 and immediately restarts discovery.
#
# Replace stop_discovery() so a successful HCI stop request produces the
# modern one-byte-type Command Complete first, removes the legacy synthetic
# pending command, and only then emits modern DISCOVERING=0.
a = s.index("static int stop_discovery(struct sock *sk, u16 index)")
b = s.find("\nstatic ", a + 1)
if b < 0:
    raise SystemExit("stop_discovery end marker not found")

new_stop = r'''static int stop_discovery(struct sock *sk, u16 index)
{
        struct hci_cp_le_set_scan_enable le_cp = {0, 0};
        struct mgmt_mode mode_cp = {0};
        struct hci_dev *hdev;
        struct pending_cmd *cmd = NULL;
        int err = -EPERM;
        u8 state;

        BT_DBG("");

        hdev = hci_dev_get(index);
        if (!hdev)
                return cmd_status(sk, index, MGMT_OP_STOP_DISCOVERY, ENODEV);

        BT_DBG("disco_state: %d", hdev->disco_state);

        hci_dev_lock_bh(hdev);

        state = hdev->disco_state;
        hdev->disco_state = SCAN_IDLE;
        del_timer(&hdev->disco_le_timer);
        del_timer(&hdev->disco_timer);

        if (state == SCAN_LE)
                err = hci_send_cmd(hdev, HCI_OP_LE_SET_SCAN_ENABLE,
                                   sizeof(le_cp), &le_cp);
        else if (state == SCAN_BR)
                err = hci_send_cmd(hdev, HCI_OP_INQUIRY_CANCEL, 0, NULL);

        cmd = mgmt_pending_find(MGMT_OP_STOP_DISCOVERY, index);

        if (err >= 0) {
                /* Response must precede DISCOVERING=0 so BlueZ removes the
                 * D-Bus discovery client before processing the state event. */
                err = cmd_complete(sk, index, MGMT_OP_STOP_DISCOVERY,
                                   &compat_discovery_type,
                                   sizeof(compat_discovery_type));

                if (cmd)
                        mgmt_pending_remove(cmd);

                if (err >= 0)
                        err = compat_mgmt_discovering(index, mode_cp.val);
        } else if (cmd) {
                mgmt_pending_remove(cmd);
        }

        hci_dev_unlock_bh(hdev);
        hci_dev_put(hdev);

        if (err < 0)
                return cmd_status(sk, index, MGMT_OP_STOP_DISCOVERY, -err);

        return err;
}
'''

s = s[:a] + new_stop + s[b:]

# The asynchronous legacy termination callback must not generate another
# STOP command completion.  It may still emit a later duplicate state event,
# but the pending command has already been removed so it cannot double-complete.
a = s.index("static void discovery_terminated(struct pending_cmd *cmd, void *data)")
b = s.index("static int pair_device(", a)
term = s[a:b]
if "cmd_complete(cmd->sk, cmd->index, MGMT_OP_STOP_DISCOVERY" in term:
    completion = (
        "\tcmd_complete(cmd->sk, cmd->index, MGMT_OP_STOP_DISCOVERY,\n"
        "\t\t     &compat_discovery_type,\n"
        "\t\t     sizeof(compat_discovery_type));\n\n"
    )
    if completion not in term:
        raise SystemExit("unexpected discovery_terminated completion form")
    term = term.replace(completion, "", 1)
    s = s[:a] + term + s[b:]

# Build-time invariants.
a = s.index("static int stop_discovery(struct sock *sk, u16 index)")
b = s.find("\nstatic ", a + 1)
stop = s[a:b]
if stop.count("cmd_complete(sk, index, MGMT_OP_STOP_DISCOVERY") != 1:
    raise SystemExit("STOP_DISCOVERY must have exactly one immediate completion")
if stop.find("cmd_complete(sk, index, MGMT_OP_STOP_DISCOVERY") > stop.find("compat_mgmt_discovering(index, mode_cp.val)"):
    raise SystemExit("STOP_DISCOVERY completion must precede DISCOVERING=0")
if "mgmt_pending_remove(cmd);" not in stop:
    raise SystemExit("STOP_DISCOVERY pending command removal missing")

a = s.index("static void discovery_terminated(struct pending_cmd *cmd, void *data)")
b = s.index("static int pair_device(", a)
term = s[a:b]
if "cmd_complete(cmd->sk, cmd->index, MGMT_OP_STOP_DISCOVERY" in term:
    raise SystemExit("late duplicate STOP_DISCOVERY completion remains")

p.write_text(s)
print("STOP_DISCOVERY response ordering patched")
