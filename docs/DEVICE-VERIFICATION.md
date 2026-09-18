# Device verification — Batch 12 update

Verification date: 17 September 2026.

Batch 12 rechecked available device tooling and connected-device inventory. No controllable Android/ADB or Apple device harness was found. All physical Android outcomes remain UNVERIFIED: PWA installation, offline reopen/force-kill persistence, camera/POD/signature, expense/receipt sync, defect/photo sync, account switching, expired-session recovery, worker update persistence and real storage pressure. Actual iOS/Safari equivalents are also UNVERIFIED. No device model, OS version or physical test result is claimed.

The earlier Batch 10 limitations below remain applicable. Current desktop regression evidence is recorded separately in BATCH-12-REPORT.md. Desktop synthetic quota, session and update tests do not establish behavior under mobile OS eviction, force-stop or background scheduling.

Physical Android: UNVERIFIED. No accessible physical device/ADB harness was found. Android version, Chrome version, installation, camera, signature touch handling, force-kill/offline reopen, account switching, expired-session reconnect and combined golden workflow were not exercised on physical hardware.

Actual iPhone/iPad and Safari: UNVERIFIED. No accessible Apple device or Safari environment was available. No WebKit emulation is represented as Safari certification.

Desktop Chrome automation is reported separately in BATCH-10-REPORT.md. It can establish browser queue/Blob persistence, compatible worker and IndexedDB upgrade behavior, synthetic quota errors, session expiry, logout cleanup and replay behavior only. Phone-width viewports are layout checks, not device verification. Installability in a persistent desktop Chrome profile is not an Android installation.

## Remaining device gate

Use a dedicated synthetic tenant on accessible HTTPS staging. Record device model, OS/browser versions and install outcome. Exercise assigned trip, offline milestone/fuel/receipt/POD/photo/signature, force-kill and offline reopen, reconnect and exactly-once server history. Repeat account A logout/account B login and expired-session recovery; inspect snapshots, pending actions, drafts and evidence isolation. Verify usable navigation, no overflow/clipping, touch signature and camera input. Record actual outcomes; do not extrapolate from desktop tests.

Browser storage remains evictable and unencrypted; unsynced device loss is not recoverable from server backup. Background execution is OS-controlled. A simulated quota rejection does not prove survival of OS eviction.

## Batch 12 executed desktop results

Final production Chrome: 35/35 passed, including offline expense/receipt and defect/photo lost-response replay, compatible worker update, IndexedDB upgrade, session/account cleanup and synthetic storage failure. A discovered stale expense-prop conflict was fixed by consulting durable local queue versions; the original failing case and new two-tab case both passed afterward. These results do not change any physical-device UNVERIFIED label.
