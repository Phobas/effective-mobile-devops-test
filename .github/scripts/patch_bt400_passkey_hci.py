from pathlib import Path

p = Path('kernel/net/bluetooth/mgmt.c')
s = p.read_text()

anchor = 'static int compat_user_passkey_reply(struct sock *sk, u16 index,\n'
if anchor not in s:
    raise SystemExit('compat_user_passkey_reply anchor not found')

compat = '''#define COMPAT_HCI_OP_USER_PASSKEY_REPLY     0x042E\n#define COMPAT_HCI_OP_USER_PASSKEY_NEG_REPLY 0x042F\nstruct compat_hci_cp_user_passkey_reply {\n\tbdaddr_t bdaddr;\n\t__le32 passkey;\n} __packed;\n\n'''
if 'COMPAT_HCI_OP_USER_PASSKEY_REPLY' not in s:
    s = s.replace(anchor, compat + anchor, 1)

repls = {
    'struct hci_cp_user_passkey_reply cp;': 'struct compat_hci_cp_user_passkey_reply cp;',
    'HCI_OP_USER_PASSKEY_NEG_REPLY': 'COMPAT_HCI_OP_USER_PASSKEY_NEG_REPLY',
    'HCI_OP_USER_PASSKEY_REPLY': 'COMPAT_HCI_OP_USER_PASSKEY_REPLY',
}
for old, new in repls.items():
    if old not in s:
        raise SystemExit(f'missing passkey HCI anchor: {old}')
    s = s.replace(old, new)

p.write_text(s)
print('Missing flo HCI user-passkey commands patched')
