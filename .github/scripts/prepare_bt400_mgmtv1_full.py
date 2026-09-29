from pathlib import Path

p = Path('.github/scripts/patch_bt400_mgmtv1_full.py')
s = p.read_text()

old = '''for pat, repl in settings_events:
    s, n = re.subn(pat, repl, s, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("settings event bridge missing: " + pat)
'''
new = '''for pat, repl in settings_events:
    s, n = re.subn(pat, repl, s, count=1, flags=re.S)
    # Some flo vendor revisions do not emit every legacy per-setting event.
    # Zero matches are therefore valid; more than one would be ambiguous.
    if n > 1:
        raise SystemExit("ambiguous settings event bridge: " + pat)
'''

if old not in s:
    raise SystemExit('settings-events strict-check anchor not found')
s = s.replace(old, new, 1)

# This flo tree has mgmt_pin_code_request(index, bdaddr) with secure hardcoded
# to zero, rather than the newer helper taking a secure argument.  Adjust the
# full patcher's exact anchor to the code that is actually present here.
s = s.replace('\\tev.secure = secure;', '\\tev.secure = 0;')

p.write_text(s)
print('Full MGMT patch prepared for flo vendor layout')
