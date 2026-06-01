---
name: vesync-recon-notes
description: pyvesync scale-support state + auth artifacts to reuse for direct fat-scale API calls (Etekcity/Cosori smart scale → fitness dashboard)
---

# VeSync smart-scale recon — 2026-06-01

Target: pull weight + body composition off Alfie's Etekcity/Cosori smart scale
into the fitness dashboard. Library: **pyvesync** (MIT). Tonight = recon + stub,
no credentials yet.

## Environment constraint

System python is **3.9.6** (`/usr/bin/python3`). pip resolved pyvesync to
**2.1.18** — the **3.x line requires Python ≥3.11**, so we are pinned to the 2.x
API. Stub is written against 2.1.18 (see `requirements.txt`). Saturn-shell honored:
no rewrite, no fork — we use 2.1.18 as-is.

## Does pyvesync 2.1.18 wrap the scale? → NO.

`from pyvesync import VeSync` exposes device modules for only these categories:

    vesyncbulb, vesyncfan, vesynckitchen, vesyncoutlet, vesyncswitch

There is **no scale / health / body-composition class**. `manager.get_devices()`
filters the raw device list down to these supported types, so the scale is
**dropped before it ever surfaces** as an object. Conclusion: pyvesync gives us
**auth + raw device listing only** — body-comp data must come from a direct call.

## Auth artifacts we CAN reuse (the useful part)

After `manager = VeSync(email, password, time_zone); manager.login()` succeeds,
the instance carries everything the cloud API needs:

| attribute            | role                                  |
|----------------------|---------------------------------------|
| `manager.token`      | session token (sent as `tk` header / `token` body) |
| `manager.account_id` | account id (`accountId` header / `accountID` body) |
| `manager.time_zone`  | tz string used in every body          |

Constants from `pyvesync/helpers.py`:
- `API_BASE_URL = 'https://smartapi.vesync.com'`
- `APP_VERSION  = '2.8.6'`
- `Helpers.req_headers(manager)` → `{accept-language, accountId, appVersion, content-type, tk, tz}`
- `Helpers.req_body_base(manager)` → `{timeZone, acceptLanguage:'en'}`
- `Helpers.req_body_auth(manager)` → `{accountID, token}`

So we authenticate through pyvesync (it handles password hashing + login), then
borrow `token`/`account_id` and POST directly to the fat-scale endpoint.

## The fat-scale endpoint

    POST https://smartapi.vesync.com/cloud/v1/deviceManaged/fatScale/getWeighData

Body is a bypass-style JSON: `req_body_base + req_body_auth` plus a `method`
and likely a date range + the scale's `uuid`/`configModule`/`subDeviceNo`.
The **exact field names are not pinned down without a live account** — community
captures show variants like `{ "method":"getWeighData", "page":1, "pageSize":100,
"configModule":..., "uuid":..., "subUserID":... }`. The stub builds a best-guess
body and logs the raw response so we can correct field names on first real run.

## Finding the scale (since get_devices() hides it)

Call the raw device-list endpoint directly:

    POST https://smartapi.vesync.com/cloud/v1/deviceManaged/devices
    body = req_body_base + req_body_auth + {method:'devices', pageNo:'1', pageSize:'100'}

Response `result.list[]` includes ALL devices with `cid`, `uuid`, `deviceType`,
`deviceName`, `configModule`. Filter where `deviceType`/`configModule` looks like
a scale (e.g. contains `ESF` / `scale` / matches Etekcity-Cosori fat-scale model).
The stub does substring matching and lets `VESYNC_DEVICE_ID` (cid) pin it.

## Open items for the real run (with creds)

1. Confirm fat-scale POST body field names against the live 401/200 response.
2. Confirm the response shape → map to weight/bodyFat/BMI/muscle/water/BMR/visceral.
3. Confirm units (kg vs lb) — VeSync returns metric; dashboard may want lb.
4. Confirm which id the endpoint wants (uuid vs cid vs subUserID).
