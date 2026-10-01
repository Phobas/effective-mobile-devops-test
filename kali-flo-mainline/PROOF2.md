# Kali flo mainline proof2

Diagnostic boot image for Nexus 7 2013 (flo).

Changes from proof1:
- Linux 7.1 APQ8064 mainline kernel
- CONFIG_PSTORE / CONFIG_PSTORE_RAM / CONFIG_PSTORE_CONSOLE
- lk2nd.pass-ramoops=zap
- simple framebuffer handoff for early console visibility

This image is intended for temporary `fastboot boot` testing only.
