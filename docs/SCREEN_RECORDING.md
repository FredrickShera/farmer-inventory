# 60-second screen recording script

Record on an emulator or phone (Android: Screen Recorder; iOS: Control Centre record; emulator: `adb shell screenrecord`).
Backend must be running and seeded (see README section 1).

| Time | Do | Say (optional) |
| --- | --- | --- |
| 0:00-0:08 | Open the app, tap **Create an account**, show the dependent dropdowns (County, then Sub-county, then Ward). Enter an invalid phone to show the inline error. | "Dropdowns come from the locations table; validation is inline." |
| 0:08-0:20 | Fix the fields, register. You land on the Inventory tab (empty state). | "Registration creates the auth user and farmer together." |
| 0:20-0:30 | Log out from Profile, then log in with the phone number and password. | "Tokens are in the Keychain / Keystore, logout wipes them." |
| 0:30-0:50 | Tap **Add inventory item**. Pick produce, enter quantity **-5** (error), then **25.5**, grade, date `2026-12-01`, price `45.50`. Double-tap **Add item** quickly. One card appears. | "Negative quantity is blocked; a double tap creates one record." |
| 0:50-1:00 | Pull to refresh; use the Status filter; open a sold item (log in as `wanjiru@coop.example` / `Passw0rd!2026` for seed data, or mark yours sold) to show the read-only view. | "Sold items are read-only." |
