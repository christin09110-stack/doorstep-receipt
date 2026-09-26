# Doorstep Receipt

Reconciles what a carrier's tracking claims against what a Ring doorbell camera
actually recorded, and produces a one-page evidence pack you can paste into a
retailer's claim form. Built for the Amazon Developer Hackathon (Ring track).

Full product spec, including the design rationale and everything this build
deliberately does not do: [`SPEC.md`](SPEC.md).

## The honest boundary, up front

**This app has never run against a live Ring device**, and says so rather than
implying otherwise. A documentation review found no documented Ring
simulator anywhere in Ring's own developer docs; a real run needs a US-located
device on an active Ring Protection plan, and clip retrieval additionally needs
a continuous-recording plan. The Ring client (`doorstep_receipt/ring_client.py`)
is written against the real, documented endpoint shapes: same base URL
(`https://api.amazonvision.com`), same JSON:API envelope, same auth header, and
is tested with a mocked HTTP layer, never a real account. The demo path replays
pre-signed webhook fixtures through the exact signature-verification function a
real webhook would hit (`/demo/replay` calls the same code as `/webhooks/ring`).
That boundary is drawn in the code (`fixtures/` on one side, `ring_client.py`
and `webhook.py` on the other) and in this paragraph, not blurred.

**This app also does not get carrier tracking data on its own.** That is the
hard half of the product and it is not solved here; see SPEC.md's "What it
deliberately does not do" for why every alternative (carrier APIs, mailbox
parsing) is worse for a third party than asking the person to hand over what
their own tracking page already shows them. `doorstep_receipt/carrier.py`
ships two adapters behind a `CarrierAdapter` interface so a better source can
be dropped in later without touching the reconciliation logic:
`TrackingPageAdapter`, backed by the multimodal reader below, which the
product now leads with, and `ManualEntryAdapter`, the always-available typed
fallback when a page can't be photographed or pasted.

## What it does

1. A Ring webhook (or, in this build, a replayed signed fixture) reports a
   `motion.human` or `button_press` event at the front door. The signature is
   verified with HMAC-SHA256 before the event is stored.
2. The person pastes a tracking number, picks the status their tracking page is
   showing ("delivered", "attempted delivery", "out for delivery"), and the
   claimed time — or pastes/photographs the tracking page itself and lets
   Bedrock read the carrier, number, status and claimed time back out
   (`POST /read`, see "Amazon Bedrock" below).
3. The reconciliation engine (`doorstep_receipt/reconcile.py`) checks whether a
   person or a knock was recorded within a time window around the claimed time,
   and produces a verdict: **consistent with camera**, **not consistent with
   camera**, or **indeterminate**. It never names or accuses a person: Ring's
   own classifier has been documented mislabeling a wheelchair as a package, so
   the output states what is on record, not a conclusion about who did what.
4. The evidence pack (`GET /claims/{id}/evidence`, or open `/` in a browser and
   click through) renders that verdict as a stamped, parchment-and-ink
   document; see SPEC.md's Design section for why this looks like a claim file
   and not a smart-home dashboard. A downloadable, hash-manifested version of
   the same pack (`GET /claims/{id}/pack`, `/pack.zip`) lets anyone check the
   exhibits were not altered after the fact (`sha256sum -c manifest.sha256`,
   or `POST /packs/verify` to check it in the browser).
5. A dispute letter (`GET /claims/{id}/letter`) is drafted from the claim's own
   facts — by Bedrock when it is reachable, by a fixed template otherwise or
   whenever the model's wording is refused by the language guard. Either way
   the letter is editable, and edits go through the same guard on save. See
   "Amazon Bedrock" below.
6. The person can correct a claim (`POST /claims/{id}/correct`) or record the
   outcome once the retailer responds (`POST /claims/{id}/outcome`); the full
   record is at `GET /claims/{id}/record`.

## Amazon Bedrock

Two features call a model, and both are honest about what happens when it is
not reachable:

- **The dispute letter** (`letter.py`) drafts from the claim's facts through a
  model preference chain (`doorstep_receipt/bedrock.py`). If Bedrock is
  unreachable, or the model's draft trips the language guard, the letter falls
  back to a fixed template with the claim's values filled in — the page says
  which path produced it, never silently.
- **The tracking-page reader** (`POST /read`, `tracking_reader.py`) lets a
  multimodal call transcribe a pasted screenshot or pasted text of a carrier's
  tracking page into carrier, number, status and claimed time. It only
  transcribes — a deterministic carrier registry (`carriers.py`) outranks the
  model whenever they disagree, and the disagreement is recorded rather than
  hidden. With no network, pasted text still parses via `tracking_text.py`'s
  regexes; a pasted image without Bedrock gets an honest "type it in yourself".

Environment variables (all optional; the app runs with none of them set):

| Variable | Default | Effect |
|---|---|---|
| `DOORSTEP_BEDROCK` | unset | `off`/`0`/`false`/`no` runs the whole app with no AWS account — both features use their fallback every time |
| `DOORSTEP_BEDROCK_MODEL` | unset | pins one model id instead of walking the preference chain |
| `DOORSTEP_BEDROCK_TIMEOUT` | `20` (seconds) | read timeout on the Bedrock client |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | your AWS CLI/env default | region Bedrock is called in |

## Run it

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# generate the signed webhook fixtures the demo replays
python fixtures/generate_fixtures.py

# run the app
uvicorn doorstep_receipt.app:app --reload
```

Run this way — typed into your own terminal — it runs for as long as your terminal
does, same as any other dev server.

Then, with the server running:

```bash
# replay the signed fixtures (a knock at 14:11, human motion at 14:13)
curl -X POST http://127.0.0.1:8000/demo/replay

# submit a claim that lands inside that window -> "consistent with camera"
curl -X POST http://127.0.0.1:8000/claims -H "Content-Type: application/json" -d '{
  "tracking_number": "1Z999AA10123456784",
  "carrier_name": "UPS",
  "status": "delivered",
  "claimed_at": "2026-09-20T14:11:00Z"
}'
# -> {"claim_id": "...", "verdict": "consistent_with_camera"}

# open the evidence pack in a browser (macOS: open, Linux: xdg-open)
# http://127.0.0.1:8000/claims/<claim_id>/evidence

# a claim with no matching events -> "not consistent with camera"
curl -X POST http://127.0.0.1:8000/claims -H "Content-Type: application/json" -d '{
  "tracking_number": "RQ123456785GB",
  "carrier_name": "Royal Mail",
  "status": "delivered",
  "claimed_at": "2026-09-20T09:00:00Z"
}'

# the number and the carrier disagree -> 400, and the app says which is which
# rather than quietly checking a Royal Mail claim against USPS's window
curl -X POST http://127.0.0.1:8000/claims -H "Content-Type: application/json" -d '{
  "tracking_number": "9400111899223197428490",
  "carrier_name": "Royal Mail",
  "status": "delivered",
  "claimed_at": "2026-09-20T09:00:00Z"
}'
```

To point the client at a real Ring account instead of fixtures, get a token from
the [Ring Developer Playground](https://developer.amazon.com/ring/console/playground)
and use `RingClient(token=...)` directly (see `doorstep_receipt/ring_client.py`).
This path is written and tested but not wired into `app.py` in this
submission, because there is no live device to point it at.

## Tests

```bash
python -m pytest tests/ -q
```

135 tests, all real assertions on behaviour: HMAC signature verification
(accepts a correctly signed body, rejects a tampered body, rejects the wrong
secret, rejects a missing header), webhook idempotency on `meta.request_id`,
the reconciliation rules for every claimed status against present/absent/
irrelevant events (a vehicle passing does not count as a delivery witness), the
manual-entry carrier adapter's validation, the Ring client against a mocked
HTTP layer including the documented `416 TIMESTAMP_NOT_FOUND` case, the
evidence pack's HTML and JSON rendering (including an explicit assertion that
no accusatory language like "lied" or "did not come" appears anywhere in
rendered output), and the FastAPI routes end to end.

## What's out of scope for this build

See SPEC.md. In short: one device per claim, US-only (matching Ring's own API),
no write-back to Ring (its only write endpoint is chime audio playback, which
this product has no use for), and no live-device run.

## Licence

MIT. Third-party font and image credits: see [`ATTRIBUTION.md`](ATTRIBUTION.md).
