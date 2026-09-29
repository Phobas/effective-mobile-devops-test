from pathlib import Path
import re

p = Path("kernel/net/bluetooth/mgmt.c")
s = p.read_text()


def patch_completion(func_name, opcode_expr):
    global s
    start = s.find(f"int {func_name}(")
    if start < 0:
        start = s.find(f"static int {func_name}(")
    if start < 0:
        raise SystemExit(f"{func_name}: start not found")
    end = s.find("\nint ", start + 4)
    end_static = s.find("\nstatic int ", start + 4)
    candidates = [x for x in (end, end_static) if x >= 0]
    end = min(candidates) if candidates else len(s)
    seg = s[start:end]

    if "rp.status = status;" not in seg:
        raise SystemExit(f"{func_name}: legacy rp.status assignment not found")
    seg = seg.replace("rp.status = status;", "rp.addr_type = 0x00;", 1)

    pat = re.compile(
        r"err = cmd_complete\(cmd->sk, index,\s*" + re.escape(opcode_expr) +
        r",\s*&rp,\s*sizeof\(rp\)\);",
        re.S,
    )
    repl = (
        "err = compat_cmd_complete_status(cmd->sk, index, " + opcode_expr +
        ", compat_hci_status(status), &rp, sizeof(rp));"
    )
    seg, n = pat.subn(repl, seg, count=1)
    if n != 1:
        raise SystemExit(f"{func_name}: cmd_complete call not found")
    s = s[:start] + seg + s[end:]


patch_completion("mgmt_pin_code_reply_complete", "MGMT_OP_PIN_CODE_REPLY")
patch_completion("mgmt_pin_code_neg_reply_complete", "MGMT_OP_PIN_CODE_NEG_REPLY")

# USER_CONFIRM reply and negative reply share this helper and pass the modern
# opcode in as an argument.
start = s.find("static int confirm_reply_complete(")
if start < 0:
    raise SystemExit("confirm_reply_complete: start not found")
end = s.find("\nint mgmt_user_confirm_reply_complete", start)
if end < 0:
    raise SystemExit("confirm_reply_complete: end not found")
seg = s[start:end]
if "rp.status = status;" not in seg:
    raise SystemExit("confirm_reply_complete: legacy rp.status assignment not found")
seg = seg.replace("rp.status = status;", "rp.addr_type = 0x00;", 1)
seg, n = re.subn(
    r"err = cmd_complete\(cmd->sk, index, opcode,\s*&rp,\s*sizeof\(rp\)\);",
    "err = compat_cmd_complete_status(cmd->sk, index, opcode, "
    "compat_hci_status(status), &rp, sizeof(rp));",
    seg,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit("confirm_reply_complete: cmd_complete call not found")
s = s[:start] + seg + s[end:]

# The earlier pairing bridge built a modern Command Complete payload, but used
# mgmt_event(..., cmd->sk).  In this old kernel the final argument is skip_sk,
# so that accidentally excluded the requester.  Command responses must be sent
# directly to the MGMT socket that issued Pair Device.
pattern = re.compile(
    r"\s*mgmt_event\(MGMT_EV_CMD_COMPLETE,\s*cmd->index,\s*&ev,\s*"
    r"sizeof\(ev\),\s*cmd->sk\);"
)
replacement = (
    "\n        compat_cmd_complete_status(cmd->sk, cmd->index, MGMT_OP_PAIR_DEVICE, "
    "mgmt_status, &ev.bdaddr, sizeof(ev.bdaddr) + sizeof(ev.addr_type));"
)
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit(f"pairing_complete requester-socket anchor count={n}")

p.write_text(s)
print("MGMT v1 PIN/SSP/pair completion responses patched")
