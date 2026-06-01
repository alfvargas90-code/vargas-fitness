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

---

# UPDATE 2026-06-01 — endpoint CRACKED, but no body-comp available (BT scale)

**Bottom line: muscle / water / BMR / visceral are NOT obtainable from the
VeSync cloud for this scale.** The history endpoint now works (no more
`-11000079`), but it returns an empty array — the cloud stores no weigh history
for a Bluetooth-only ESF-551. Staying on `getUserInfo` (weight + BF%) is the
correct end state. Details below so future-Penny doesn't re-walk this.

## What `-11000079` actually means → **"illegal argument"** (malformed body)

Confirmed live: a v2 `getWeighingDataV2` body that mixed `startTime/endTime`
(a v1 field) with the v2 endpoint returned exactly `code=-11000079 msg="illegal
argument"`. So every prior `-11000079` was a **bad request-body shape**, not an
auth / subscription / device-support / sub-user problem. The endpoint was
reachable the whole time — we were sending the wrong field set.

## The fix that stopped the errors (request shape that returns code=0)

Two things the earlier attempts got wrong:
- **`appVersion` must be `3.0.20`** (the app value in the issue-#56 capture), not
  pyvesync's `2.8.6`.
- **Headers must be the lowercase app-style block**, not `Helpers.req_headers`:
  ```
  accept: application/json
  tk: <token>
  accountid: <accountID>
  tz: America/Chicago
  accept-language: en
  appversion: 3.0.20
  content-type: application/json
  User-Agent: okhttp/3.12.1
  ```

### WORKING request — v2 (Bluetooth scales: cid=null, keyed on macID)
```
POST https://smartapi.vesync.com/cloud/v2/deviceManaged/getWeighingDataV2
{
  "traceId": "<epoch>", "token": "<tok>", "accountID": "<id>",
  "timeZone": "America/Chicago", "acceptLanguage": "en", "appVersion": "3.0.20",
  "phoneBrand": "SM-G973U1", "phoneOS": "Android 10",
  "method": "getWeighingDataV2",
  "configModule": "BT_SCL_ESF551_US",
  "macID": "<device macID>",
  "uuid": "<device uuid>",
  "subUserID": "0",
  "allData": true, "page": 1, "pageSize": 100
}
→ HTTP 200  code=0  msg="request success"  result={"weightDatas": []}   ← EMPTY
```
Important: use **`allData:true` + page/pageSize** for v2. Do NOT add
`startTime/endTime` — that mix triggers `-11000079`.

### WORKING request — v1 (WiFi scales: keyed on cid + startTime/endTime)
```
POST https://smartapi.vesync.com/cloud/v1/deviceManaged/fatScale/getWeighData
{ ...same auth/appVersion/header block...,
  "method":"getWeighData", "startTime":0, "endTime":<epoch>,
  "configModule":"<cfg>", "cid":"<cid>",
  "pageSize":100, "order":"desc", "index":0, "flag":1 }
→ HTTP 200  code=0  msg="request success"  result=null   ← null (cid is null on this BT scale)
```

## Why it's empty — this ESF-551 is **Bluetooth-only**

Device record (live):
```
deviceType=ESF-551  configModule=BT_SCL_ESF551_US  connectionType=BT
cid=null  connectionStatus=offline  firmware=R0010V1004
uuid=3DC9E9D2-...  macID=D0:4D:00:42:E5:66
```
BT scales sync readings **scale → phone over Bluetooth** and store them in the
VeSync app. They do **not** push a queryable per-reading history to the cloud.
`weightDatas` came back `[]` for every subUserID tried (`0`, `001`, `1`, and the
real account id `16153776`) — empty data, not a permission gate. WiFi fat scales
(cid != null) DO populate `weightDatas`, but Alfie's is BT.

## Sub-user / member-list endpoints don't exist on this account

`getAllUserInfo`, `getSubUserList`, `getMemberList`, fatScale `listSubUser` all
returned `code=-11102086 "internal error"` — not exposed here. No subUserID to
discover anyway.

## Even if weightDatas were populated, no computed metrics come back

Per issue #56 captures, a non-empty `getWeighData`/`getWeighingDataV2` row is:
`weigh_kg, weigh_lb, impedence/impedance, timestamp, unit, gender, age, heightCm,
arithmeticVersion, bfr (often null)`. The cloud returns **raw bioimpedance**, not
muscle/water/BMR/visceral — the VeSync app computes those locally from impedance
+ biometrics via the BIA formula keyed by `arithmeticVersion`. That formula is
not documented publicly.

## getUserInfo FULL dump (Tier 4) — body-comp fields confirmed ABSENT

Searched the full result: it carries `weightG`, `initialWeightG`, `initialBfr`
(15.5), `targetBfr` (13.0), `heightCm` (170), `gender`, `birthday`,
`statusUpdateTimestamp` (1773250901 = 2026-03-11). **No** `muscle`, `water`,
`bmr`, `visceral`, `vfr`, `proteinRate`, or `impedance` field anywhere. So the
profile snapshot tops out at weight + body-fat-rate — exactly what sync.py
already reads.

## Recommendation

**Stay on `getUserInfo` for weight + BF% (current sync.py is correct).** Do NOT
wire the weigh-data endpoint into sync.py — it returns empty for this BT scale,
so it would be dead code. Revisit only if:
- Alfie buys a **WiFi** VeSync fat scale (cid != null) → the v1 shape above will
  return real rows (still impedance, not computed comp).
- We want muscle/water/BMR/visceral badly enough to **mitmproxy the iOS app** and
  capture the local BLE-derived values, or re-implement the BIA formula from
  impedance ourselves (no public spec; reverse-engineering effort).

Reusable working request bodies are logged verbatim above so this never needs
re-deriving. Recon scripts (`recon.py`, `recon2.py`) were throwaway and removed.
