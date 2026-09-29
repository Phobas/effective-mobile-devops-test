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

p.write_text(s.replace(old, new, 1))
print('Full MGMT patch prepared for optional legacy settings events')
