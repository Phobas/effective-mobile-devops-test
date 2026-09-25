from pathlib import Path

# ASUS USB-BT400 + old flo HCI driver-data ABI.
p = Path('kernel/drivers/bluetooth/btusb.c')
s = p.read_text()
if 'USB_DEVICE(0x0b05, 0x17cb)' not in s:
    needle = '\t{ USB_DEVICE(0x0a5c, 0x21e1) },\n'
    repl = needle + '\n\t/* ASUS USB-BT400 - Broadcom BCM20702A0. */\n\t{ USB_DEVICE(0x0b05, 0x17cb), .driver_info = BTUSB_BROKEN_ISOC },\n'
    if needle not in s:
        raise SystemExit('BT400 ID anchor not found')
    s = s.replace(needle, repl, 1)
if 'static void btusb_compat_destruct(struct hci_dev *hdev)' not in s:
    needle = 'static struct usb_driver btusb_driver;\n'
    repl = needle + '\nstatic void btusb_compat_destruct(struct hci_dev *hdev)\n{\n}\n'
    if needle not in s:
        raise SystemExit('btusb declaration anchor not found')
    s = s.replace(needle, repl, 1)
if 'hdev->destruct = btusb_compat_destruct;' not in s:
    needle = '\thdev->notify   = btusb_notify;\n'
    repl = needle + '\thdev->destruct = btusb_compat_destruct;\n\thdev->owner    = THIS_MODULE;\n'
    if needle not in s:
        raise SystemExit('HCI callback anchor not found')
    s = s.replace(needle, repl, 1)
s = s.replace('hci_get_drvdata(hdev)', 'hdev->driver_data')
s = s.replace('hci_set_drvdata(hdev, data);', 'hdev->driver_data = data;')
p.write_text(s)

# BlueZ 5.x uses HCI control channel 3; legacy flo uses 1.
p = Path('kernel/net/bluetooth/hci_sock.c')
s = p.read_text()
old = '\tif (haddr.hci_channel > HCI_CHANNEL_CONTROL)\n\t\treturn -EINVAL;\n\n\tif (haddr.hci_channel == HCI_CHANNEL_CONTROL && !enable_mgmt)\n\t\treturn -EINVAL;\n'
new = '\tif (haddr.hci_channel == 3)\n\t\thaddr.hci_channel = HCI_CHANNEL_CONTROL;\n\telse if (haddr.hci_channel > HCI_CHANNEL_CONTROL)\n\t\treturn -EINVAL;\n\n\tif (haddr.hci_channel == HCI_CHANNEL_CONTROL && !enable_mgmt)\n\t\treturn -EINVAL;\n'
if old not in s:
    raise SystemExit('HCI control-channel anchor not found')
s = s.replace(old, new, 1)
p.write_text(s)

# Modern MGMT event wire layouts.
h = Path('kernel/include/net/bluetooth/mgmt.h')
s = h.read_text()
old = 'struct mgmt_ev_cmd_complete {\n\t__le16 opcode;\n\t__u8 data[0];\n} __packed;'
new = 'struct mgmt_ev_cmd_complete {\n\t__le16 opcode;\n\t__u8 status;\n\t__u8 data[0];\n} __packed;'
if old not in s:
    raise SystemExit('CMD_COMPLETE struct anchor not found')
s = s.replace(old, new, 1)
old = 'struct mgmt_ev_cmd_status {\n\t__u8 status;\n\t__le16 opcode;\n} __packed;'
new = 'struct mgmt_ev_cmd_status {\n\t__le16 opcode;\n\t__u8 status;\n} __packed;'
if old not in s:
    raise SystemExit('CMD_STATUS struct anchor not found')
s = s.replace(old, new, 1)
h.write_text(s)

p = Path('kernel/net/bluetooth/mgmt.c')
s = p.read_text()

# CMD_COMPLETE carries explicit status in modern MGMT.
old = '\tev = (void *) skb_put(skb, sizeof(*ev) + rp_len);\n\tput_unaligned_le16(cmd, &ev->opcode);\n\n\tif (rp)\n\t\tmemcpy(ev->data, rp, rp_len);'
new = '\tev = (void *) skb_put(skb, sizeof(*ev) + rp_len);\n\tput_unaligned_le16(cmd, &ev->opcode);\n\tev->status = 0;\n\n\tif (rp)\n\t\tmemcpy(ev->data, rp, rp_len);'
if old not in s:
    raise SystemExit('CMD_COMPLETE writer anchor not found')
s = s.replace(old, new, 1)

# BlueZ 5.66 requires MGMT >= 1.0.
old = '#define MGMT_VERSION\t0\n#define MGMT_REVISION\t1'
new = '#define MGMT_VERSION\t1\n#define MGMT_REVISION\t0'
if old not in s:
    raise SystemExit('MGMT version anchor not found')
s = s.replace(old, new, 1)

# Replace legacy READ_INFO response with MGMT v1 wire format.
start = s.find('static int read_controller_info(struct sock *sk, u16 index)')
end = s.find('static void mgmt_pending_free_worker', start)
if start < 0 or end < 0:
    raise SystemExit('READ_INFO function anchors not found')
func = '''static int read_controller_info(struct sock *sk, u16 index)
{
	struct mgmt_rp_read_info_v1 {
		bdaddr_t bdaddr;
		__u8 version;
		__le16 manufacturer;
		__le32 supported_settings;
		__le32 current_settings;
		__u8 dev_class[3];
		__u8 name[MGMT_MAX_NAME_LENGTH];
		__u8 short_name[11];
	} __packed rp;
	struct hci_dev *hdev;
	u32 supported, current_settings;

	BT_DBG("sock %p hci%u", sk, index);
	hdev = hci_dev_get(index);
	if (!hdev)
		return cmd_status(sk, index, MGMT_OP_READ_INFO, 0x11);

	hci_del_off_timer(hdev);
	hci_dev_lock_bh(hdev);
	set_bit(HCI_MGMT, &hdev->flags);
	memset(&rp, 0, sizeof(rp));

	bacpy(&rp.bdaddr, &hdev->bdaddr);
	rp.version = hdev->hci_ver;
	put_unaligned_le16(hdev->manufacturer, &rp.manufacturer);

	/* Basic MGMT v1 settings only. */
	supported = 0x00000001 | 0x00000002 | 0x00000008 |
		    0x00000010 | 0x00000080;
	current_settings = 0x00000010 | 0x00000080;
	if (test_bit(HCI_UP, &hdev->flags))
		current_settings |= 0x00000001;
	if (test_bit(HCI_PSCAN, &hdev->flags))
		current_settings |= 0x00000002;
	if (test_bit(HCI_ISCAN, &hdev->flags))
		current_settings |= 0x00000008;

	put_unaligned_le32(supported, &rp.supported_settings);
	put_unaligned_le32(current_settings, &rp.current_settings);
	memcpy(rp.dev_class, hdev->dev_class, sizeof(rp.dev_class));
	memcpy(rp.name, hdev->dev_name, sizeof(hdev->dev_name));

	hci_dev_unlock_bh(hdev);
	hci_dev_put(hdev);
	return cmd_complete(sk, index, MGMT_OP_READ_INFO, &rp, sizeof(rp));
}

'''
s = s[:start] + func + s[end:]

# Legacy opcode values collide with modern BlueZ commands. During this
# compatibility probe, reject these instead of invoking the wrong handler.
replacements = [
    ('\tcase MGMT_OP_REMOVE_KEY:\n\t\terr = remove_key(sk, index, buf + sizeof(*hdr), len);\n\t\tbreak;',
     '\tcase MGMT_OP_REMOVE_KEY:\n\t\terr = cmd_status(sk, index, opcode, 0x01);\n\t\tbreak;'),
    ('\tcase MGMT_OP_DISCONNECT:\n\t\terr = disconnect(sk, index, buf + sizeof(*hdr), len);\n\t\tbreak;',
     '\tcase MGMT_OP_DISCONNECT:\n\t\terr = cmd_status(sk, index, opcode, 0x01);\n\t\tbreak;'),
    ('\tcase MGMT_OP_GET_CONNECTIONS:\n\t\terr = get_connections(sk, index);\n\t\tbreak;',
     '\tcase MGMT_OP_GET_CONNECTIONS:\n\t\terr = cmd_status(sk, index, opcode, 0x01);\n\t\tbreak;'),
    ('\tcase MGMT_OP_PIN_CODE_REPLY:\n\t\terr = pin_code_reply(sk, index, buf + sizeof(*hdr), len);\n\t\tbreak;',
     '\tcase MGMT_OP_PIN_CODE_REPLY:\n\t\terr = cmd_status(sk, index, opcode, 0x01);\n\t\tbreak;'),
    ('\tcase MGMT_OP_PIN_CODE_NEG_REPLY:\n\t\terr = pin_code_neg_reply(sk, index, buf + sizeof(*hdr), len);\n\t\tbreak;',
     '\tcase MGMT_OP_PIN_CODE_NEG_REPLY:\n\t\terr = cmd_status(sk, index, opcode, 0x01);\n\t\tbreak;'),
]
for old, new in replacements:
    if old not in s:
        raise SystemExit('Legacy opcode guard anchor not found: ' + old.splitlines()[0])
    s = s.replace(old, new, 1)

p.write_text(s)
