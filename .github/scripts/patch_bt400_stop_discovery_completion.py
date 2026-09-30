from pathlib import Path

p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()

# BlueZ 5.66 waits for a terminal response to MGMT_OP_STOP_DISCOVERY.
# The legacy flo SCAN_BR path completes HCI Inquiry Cancel through
# discovery_terminated(), but that callback only emitted DISCOVERING=0 and
# removed the pending command. As a result BlueZ saw the state event yet kept
# the MGMT request pending forever and subsequent scan requests returned
# org.bluez.Error.InProgress.
#
# Make discovery_terminated() the single owner of successful STOP_DISCOVERY
# completion for both BR/EDR and LE termination paths.
a = s.index("static void discovery_terminated(struct pending_cmd *cmd, void *data)")
b = s.index("static void discovery_rsp(struct pending_cmd *cmd, void *data)", a)
seg = s[a:b]

if "cmd_complete(cmd->sk, cmd->index, MGMT_OP_STOP_DISCOVERY" not in seg:
    event_anchor = "\tcompat_mgmt_discovering(cmd->index, ev.val);\n"
    if event_anchor not in seg:
        raise SystemExit("discovery_terminated modern event anchor not found")
    completion = (
        "\tcmd_complete(cmd->sk, cmd->index, MGMT_OP_STOP_DISCOVERY,\n"
        "\t\t     &compat_discovery_type,\n"
        "\t\t     sizeof(compat_discovery_type));\n\n"
    )
    seg = seg.replace(event_anchor, completion + event_anchor, 1)

s = s[:a] + seg + s[b:]

# The legacy SCAN_LE immediate-stop path called discovery_terminated() and then
# sent a second command-complete itself. Since the callback now owns completion,
# remove that duplicate response while preserving the successful HCI result.
a = s.index("static int stop_discovery(struct sock *sk, u16 index)")
b = s.index("static int resolve_name(", a)
seg = s[a:b]

needle = (
    "\t\t\tmgmt_pending_foreach(MGMT_OP_STOP_DISCOVERY, index,\n"
    "\t\t\t\t\t\tdiscovery_terminated, NULL);\n\n"
    "\t\t\terr = cmd_complete(sk, index, MGMT_OP_STOP_DISCOVERY,\n"
    "\t\t\t\t\t\t&compat_discovery_type,\n"
    "\t\t\t\t\t\tsizeof(compat_discovery_type));"
)
replacement = (
    "\t\t\tmgmt_pending_foreach(MGMT_OP_STOP_DISCOVERY, index,\n"
    "\t\t\t\t\t\tdiscovery_terminated, NULL);"
)
if needle not in seg:
    raise SystemExit("SCAN_LE duplicate STOP_DISCOVERY completion anchor not found")
seg = seg.replace(needle, replacement, 1)
s = s[:a] + seg + s[b:]

# Build-time invariants: one terminal success response lives in
# discovery_terminated(), and no second immediate completion remains in
# stop_discovery().
a = s.index("static void discovery_terminated(struct pending_cmd *cmd, void *data)")
b = s.index("static void discovery_rsp(struct pending_cmd *cmd, void *data)", a)
term = s[a:b]
if term.count("cmd_complete(cmd->sk, cmd->index, MGMT_OP_STOP_DISCOVERY") != 1:
    raise SystemExit("STOP_DISCOVERY termination completion invariant failed")
if "compat_mgmt_discovering(cmd->index, ev.val);" not in term:
    raise SystemExit("STOP_DISCOVERY discovering event invariant failed")

a = s.index("static int stop_discovery(struct sock *sk, u16 index)")
b = s.index("static int resolve_name(", a)
stop = s[a:b]
if "cmd_complete(sk, index, MGMT_OP_STOP_DISCOVERY" in stop:
    raise SystemExit("duplicate immediate STOP_DISCOVERY completion remains")

p.write_text(s)
print("STOP_DISCOVERY completion bridge patched")
