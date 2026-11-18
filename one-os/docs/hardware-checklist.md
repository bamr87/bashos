# Hardware checklist (PLAN §9)

Run before tagging a release on at least: one modern UEFI laptop (Secure Boot on),
one older BIOS/CSM machine, one desktop with wired Ethernet. Record results in
`docs/hardware-results.md` (model, firmware version, pass/fail, notes).

- [ ] Menu appears; aliases and theme correct
- [ ] Home base boots; Wi-Fi connects; GPU/display OK
- [ ] Persistence survives reboot (create a file in `~`, reboot, check)
- [ ] netboot.xyz loads over wired Ethernet; reaches a distro installer
- [ ] USB-Ethernet adapter at the iPXE stage (record: works / doesn't)
- [ ] `sudo oneos-install` to the internal disk over Wi-Fi; target boots without the stick
- [ ] Windows ISO boots to setup (if supplied in `local-isos/`)
- [ ] Secure Boot: MOK enrollment flow — photograph each screen
  1. "Verification failed: (0x1A) Security Violation" → OK
  2. Perform MOK management → Enroll key from disk → `VTOYEFI` → `ENROLL_THIS_KEY_IN_MOKMANAGER.cer`
  3. Continue → Yes → Reboot
