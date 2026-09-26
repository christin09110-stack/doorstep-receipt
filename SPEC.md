# Doorstep Receipt

## What it does

A carrier scans a parcel "delivered." Your doorbell camera is the only independent
witness on the property. Doorstep Receipt puts the two accounts next to each other:
it pulls the Ring event history around the claimed delivery time, checks whether a
person or a knock was actually recorded in that window, and produces one page you can
paste into a retailer's claim form. It does not accuse a driver of lying. It states
what the camera did and did not record, with timestamps.

## Who for

Someone who has just been told "delivered" by a tracking page, was not home (or was
home and heard nothing), and is about to have the same argument every claims desk
runs on a loop: "our system says it arrived." The 2025 Ofcom survey of 4,058 UK
adults found 16% had a carrier claim no attempt was made while they were home, and a
separate read of 691 "marked delivered but never received" posts on r/amazonprime
found only 11 mentioned camera footage of any brand. People who own the exact
evidence that would settle the argument mostly do not think to use it. This app is
the five minutes of work between having the footage and having a claim form filled
in correctly.

## The one screen that carries the demo

A single claim page, `GET /claims/{id}/evidence`. Top: a stamped verdict, either
CONSISTENT WITH CAMERA or NOT CONSISTENT WITH CAMERA, in the colour of a wax seal
against a plain paper backdrop (see Design, below). Below it: the claimed delivery
window, the Ring events found inside that window (or the empty set, shown as an
empty set, not hidden), the watermarked snapshot reference and clip reference if any
recording exists, and a pre-written sentence, in plain English, ready to paste into a
retailer's claim form. That is the whole product. There is no dashboard, no feed, no
second screen, because the product's value is the one page, not an app you check.

Demo path: `POST /webhooks/ring` receives (or, without hardware, replays from
`fixtures/signed_webhooks/`) a `motion_detected` or `button_press` event; separately
the user pastes a tracking number and a claimed status into `POST /claims`; the
evidence page reconciles the two and renders.

## What it deliberately does not do

**It does not get carrier tracking data on its own, and it says so.** This is the
load-bearing limitation of the whole product, not an edge case, and it is designed
around rather than hidden:

- Carrier tracking APIs (UPS, FedEx, Royal Mail, USPS) are merchant integrations.
  They authenticate a shipper account, not a recipient, and none of them will hand a
  consumer app a bearer token for someone else's package.
- Reading a user's inbox for the carrier's own dispatch and delivery emails would
  work, but it needs Gmail's restricted scopes and an annual third-party security
  assessment, a heavier compliance lift than the Ring certification this app is
  built against.
- So the least bad route, and the one this app builds and ships, is: **the person
  hands over what their own tracking page is already showing them** — by
  photographing or pasting the page itself, or, failing that, by typing the
  tracking number, status and claimed time in by hand. `carrier.py` is
  written as a `CarrierAdapter` interface so that if a future carrier API, or
  a future scoped inbox read, becomes available, it plugs into the same
  reconciliation engine without touching it. Today there are two adapters:
  `TrackingPageAdapter`, backed by a multimodal model that reads the four
  facts back out of the page, which the product leads with now, and
  `ManualEntryAdapter`, the typed fallback for when a page can't be
  photographed or pasted, or the model is unreachable. The README does not
  pretend otherwise.
- This is a real cost, not a free choice. Citizens Advice's own number is that a
  third of people with a delivery problem take no action because they do not think
  it will help. Asking that person to also type a tracking number is asking the
  person least likely to act to do one more thing. The app's only answer to that is
  to make the one thing it asks for take under fifteen seconds and to make what comes
  back worth the fifteen seconds.

**It does not identify or accuse a person.** Ring's own classifier has been
documented mislabeling a wheelchair as a package. Output is phrased as "no arrival
was recorded in this window" or "a person was recorded at the door at 14:11", never
"the driver lied" or "the courier did not come." The reconciliation engine has no
verdict category for driver dishonesty, only for what is and is not on record.

**It does not run against a live Ring device in this submission.** Platform
research found no documented Ring simulator: a real run needs a US-located device on an active
Ring Protection plan, and clip retrieval additionally needs a continuous-recording
plan or it returns `416 TIMESTAMP_NOT_FOUND`. The Ring client (`ring_client.py`)
is written against the real endpoint shapes, real JSON:API envelope, and real auth
header, and is exercised by tests with a mocked HTTP layer plus fixture payloads
shaped exactly like the documented response bodies. The demo path replays
HMAC-signed webhook fixtures through the same signature-verification code a real
Ring webhook would hit. This boundary is drawn in the code (`fixtures/` versus
`ring_client.py`) and stated here rather than blurred.

**It does not have delivery history from before a user installs it.** Ring's event
history is time-gated to the moment consent was granted; there is no backfill. A
claim can only be reconciled against events the app was already watching for.

**It does not file the claim.** It produces the paragraph and the attachments a
retailer's own claim form asks for. The retailer decides the outcome.

## Design

Checked against an existing palette inventory before picking anything: nothing
already in use elsewhere runs a parchment ground with a sealing-wax red or
muted forest-green accent. The nearest alternatives were either saturated,
screen-lit palettes, or light warm-neutral grounds that don't sit in this
parchment/ink family and don't pair with a stamp-red accent.

Ground: a **deep parchment** colour, not the bright cream or blush any sibling
project uses, closer to aged paper than a UI surface. Accent: **sealing-wax
red** for a disputed verdict, **muted forest green** for a confirmed one: the
two colours a physical claims stamp would actually come in, not a UI palette.
Text is a near-black ink colour, set in a monospace face for every timestamp and
event-log row so the log reads like a ledger entry, not a card.

Why this pairing suits this product specifically: the whole point of Doorstep
Receipt is that its output is not an app screen, it is a document: the thing
someone attaches to a claim form. So the design has to stop looking like
software the moment it is the artefact itself. Parchment and a wax-stamp red or
green read as "claim file," not "smart-home dashboard," which is exactly the
distinction the product is drawing: this is evidence, not a notification.

Structure borrows the shape of a stamped legal document (masthead, a stamped
verdict block, a body in defined sections, a footer disclaimer) rather than any
sibling project's shell: none of the listed shells (left sidebar, top nav with
a metrics strip, centred hero with cards, left rail) fit a single-document
product, so this one is not a variant of any of them. There is no dashboard
chrome to keep distinct from a sibling because there is no dashboard: the one
screen this product ships is the evidence pack itself, and it is designed to be
convincing as a document first, an app screen a distant second. No blue, no
gradients, no card shadows, no rounded chat-bubble UI anywhere in it.

## Out of scope for this hackathon build

- Multi-device households (one Ring device per claim in this build).
- Non-US locales (Ring's own API is US-only; the app does not pretend otherwise).
- Any write back to Ring (the API has one write endpoint, chime playback, and this
  product has no use for it).
