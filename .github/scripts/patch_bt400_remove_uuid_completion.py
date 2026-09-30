from pathlib import Path

p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()

old = '''\tif (memcmp(cp->uuid, bt_uuid_any, 16) == 0) {
\t\terr = hci_uuids_clear(hdev);
\t\tgoto unlock;
\t}
'''

new = '''\tif (memcmp(cp->uuid, bt_uuid_any, 16) == 0) {
\t\terr = hci_uuids_clear(hdev);
\t\tif (err < 0) {
\t\t\terr = cmd_status(sk, index, MGMT_OP_REMOVE_UUID, -err);
\t\t\tgoto unlock;
\t\t}

\t\t/* BlueZ uses an all-zero UUID to clear the controller UUID list.
\t\t * The legacy flo MGMT implementation returned from this fast path
\t\t * without a Command Complete event, leaving BlueZ's MGMT queue
\t\t * permanently blocked. Always complete the REMOVE_UUID request.
\t\t */
\t\terr = cmd_complete(sk, index, MGMT_OP_REMOVE_UUID, NULL, 0);
\t\tgoto unlock;
\t}
'''

if old not in s:
    if "legacy flo MGMT implementation returned from this fast path" in s:
        raise SystemExit("REMOVE_UUID all-zero completion patch already present")
    raise SystemExit("REMOVE_UUID all-zero fast-path anchor not found")

s = s.replace(old, new, 1)

# Build-time invariants: the zero-UUID fast path must both clear the UUIDs and
# send a terminal MGMT response so BlueZ can drain its serialized command queue.
start = s.index("static int remove_uuid(")
end = s.index("static int set_dev_class(", start)
seg = s[start:end]
required = [
    "hci_uuids_clear(hdev)",
    "cmd_complete(sk, index, MGMT_OP_REMOVE_UUID, NULL, 0)",
    "cmd_status(sk, index, MGMT_OP_REMOVE_UUID, -err)",
]
for token in required:
    if token not in seg:
        raise SystemExit("REMOVE_UUID completion invariant missing: " + token)

p.write_text(s)
print("Patched REMOVE_UUID all-zero completion path")
