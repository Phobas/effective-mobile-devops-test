from pathlib import Path

p = Path('kernel/net/bluetooth/hci_event.c')
s = p.read_text()

old = '''\tif (!test_bit(HCI_LINK_KEYS, &hdev->flags))\n\t\treturn;\n\n\thci_dev_lock(hdev);'''
new = '''\tif (!test_bit(HCI_LINK_KEYS, &hdev->flags)) {\n\t\t/* BlueZ 5.66 may not have populated the legacy HCI_LINK_KEYS\n\t\t * flag because its MGMT LOAD_LINK_KEYS opcode/layout differs\n\t\t * from this old flo kernel.  Never leave the controller waiting\n\t\t * for a Link Key Request response: explicitly report that no\n\t\t * stored key exists so Secure Simple Pairing can continue. */\n\t\thci_send_cmd(hdev, HCI_OP_LINK_KEY_NEG_REPLY, 6, &ev->bdaddr);\n\t\treturn;\n\t}\n\n\thci_dev_lock(hdev);'''

if old not in s:
    raise SystemExit('HCI_LINK_KEYS early-return anchor not found')

s = s.replace(old, new, 1)
p.write_text(s)
print('Link Key Request no-key fallback patched')
