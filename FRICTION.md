# Friction log: Doorstep Receipt

Rows added as they happened, not reconstructed afterward. Two findings arrived after the
table was closed, during an audit pass that read the rendered document instead of the
test output; they are in prose underneath because they need code to be legible.

| # | Task attempted | Steps taken | Expected | Actual | Severity | Workaround | Suggestion |
|---|---|---|---|---|---|---|---|
| 1 | Reach a first real Ring API call, before designing anything around one. | Read the get-started, develop and certify pages in order, looking for the step a developer without hardware takes. | A sandbox, a demo tenant, or a documented fixture set. | None of the three. Every path terminates at a Ring device registered to a US address on an active Ring Protection subscription, with staging capped at ten users. The glossary and FAQ both use the word "sandbox"; the Test section of the same reference says to use your personal account and devices; no sandbox host or auth flow is published anywhere. The hackathon Resources page states a physical Ring device is not required, which the developer documentation does not support. | Blocker | Everything in this app is built at the HTTP client boundary (`doorstep_receipt/ring_client.py`) against documented shapes, driven by HMAC-signed fixture webhooks. No request has left this machine. | Reconcile the hackathon page with the developer docs, and either publish the sandbox or remove the word. A read-only demo tenant with synthetic devices and a week of canned history would remove this row and most of rows 2 and 7 with it. |
| 2 | Confirm the starter kit is Python, per the build brief's stated reason. | `curl` the GitHub API tree for `AmazonAppDev/ring-api-helloworld`, then raw-fetch `README.md`, `lib/auth.ts`, `scripts/list_devices.py`, `scripts/event_history.py`, `scripts/device_status.py`. | A Python repo, matching "the Ring starter is Python." | The starter is a Next.js/TypeScript app (`app/`, `lib/`) with a `scripts/` subfolder of standalone Python API-explorer scripts. Only `scripts/` is Python; the product surface — live video, webhook dashboard, SSE — is TypeScript. | Low | None needed. The brief's premise is directionally true and the scripts layer is the part we copied: same `API_BASE = "https://api.amazonvision.com"`, same JSON:API `{"data": {...}}` envelope, same `Authorization: Bearer` header shape. | Say plainly in onboarding that the starter is a TypeScript web app with a Python scripts layer, so nobody scopes a Python-only build expecting parity with the dashboard features that only exist in the TS half. |
| 3 | Find the Ring webhook signature scheme to implement real HMAC verification. | Re-read the Ring section of `research/PLATFORM-FACTS.md` and the topic file's "Webhook events" section. | A documented signing scheme with a header format and a canonicalisation rule: what exactly gets hashed, raw body or body plus timestamp. | Both sources state only "HMAC-SHA256 signature in `X-Signature`, must return 2xx within 5 seconds, deduplicate on `meta.request_id`". No canonicalisation example, no timestamp or nonce header named, no worked signature. Neither links a page that shows the recipe. | Medium | Implemented the one interpretation the two-sentence spec supports: HMAC-SHA256 over the raw request body, hex digest, compared against `X-Signature`. Documented the assumption in `webhook.py`'s docstring and in the README, so nobody reads the code as more certain than the docs are. | Publish the exact recipe next to the sentence that says signatures exist, the way Stripe and GitHub do: a sample body, a sample secret, the resulting header. And name the replay-protection header, or say there is none, because without one every faithful implementation of this scheme is replayable and every integrator will discover that separately. |
| 4 | Decide whether footage could back a disputed delivery. | Read `POST /v1/devices/{id}/media/video/download`. | A clip for any timestamp inside the retention window. | *"If the camera was not recording at the requested timestamp, you will receive a 416 TIMESTAMP_NOT_FOUND error."* Continuous recording is a paid tier, and the window a delivery dispute cares about is the minute before the event that triggered the recording, which is exactly what an event-only device does not have. So the strongest evidence this product could carry is available only to households on a subscription, and the failure for everyone else is a `416` on a well-formed request. | High | No clip path. The dispute pack is built from the event log, the tracking page reading and the coverage record. That is a weaker artefact and the README says so. | Document the plan-tier gate in the endpoint's own description rather than once in passing in another section. A `416` reads as a bad range request, not as a billing boundary, and an integrator will spend an afternoon on the timestamp arithmetic before suspecting the subscription. |
| 5 | Decide the carrier-data source before writing `carrier.py`. | Re-read the topic file's "strongest argument against it" section and the brief's instruction to pick the least-bad route and be honest about it. | A design decision, not a bug, but it cost real thinking time: every route — merchant-side carrier APIs, mailbox parsing, manual entry — is bad in a different way. | Picked manual tracking-number and status entry behind a `CarrierAdapter` interface so the choice is swappable, and wrote the cost of it into `SPEC.md`: a third of people already do not act on delivery problems, per Citizens Advice, and a product that asks them to type a tracking number is asking the group least likely to comply. | Low | The documented design decision itself. | N/A |
| 6 | Call Bedrock for the first time, using the model the upgrade brief named as verified. | `aws bedrock list-foundation-models --region us-east-1` showed `anthropic.claude-sonnet-5` and `anthropic.claude-opus-5`, exactly as the brief said. Wrote a `Converse` call against `us.anthropic.claude-sonnet-5`, then against the bare `anthropic.claude-sonnet-5`. | A model returned by `ListFoundationModels` for my account and region to be invokable by my account in that region. | `AccessDeniedException: anthropic.claude-sonnet-5 is not available for this account` on both. `ListFoundationModels` returns the service catalogue rather than an entitlement list, and nothing in the response distinguishes the two. Probed eight candidates by hand to find which answer: `us.anthropic.claude-sonnet-4-6`, `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, `us.anthropic.claude-haiku-4-5-20251001-v1:0` and `us.anthropic.claude-opus-4-6-v1` do; the Sonnet 5 and Opus 5 ids do not; and `anthropic.claude-haiku-4-5-20251001-v1:0` without the `us.` prefix fails with a third error again. | High | Shipped a preference chain rather than a model id. `bedrock.MODEL_PREFERENCE` is tried in order and the first that answers is kept for the process, with `AccessDeniedException`, `ResourceNotFoundException` and `ValidationException` treated as "try the next" and everything else as a real failure. Costs one wasted call on a cold start and removes a whole class of demo-day death. | `ListFoundationModels` should carry a per-model entitlement field, or `ListInferenceProfiles` should be documented as the list you can actually call. Today the only way to know whether a listed model is invokable is to invoke it, and the answer arrives at runtime rather than at deploy, which means it arrives during the demo for anyone who did not check. |
| 7 | Work out which id shape to use: bare model id, `us.` inference profile, or `global.` inference profile. | Tried all three for the models that do work. | One canonical id per model. | Three shapes, three failure modes, and the error messages do not tell you which shape you needed. The bare id returns `ValidationException: Invocation of model ID anthropic.claude-haiku-4-5-... with on-demand throughput isn't supported`, which is a sentence about throughput and not about the thing that is wrong, which is that you need a cross-region inference profile. `us.` and `global.` both work for the models I could reach. | Medium | Only `us.`-prefixed inference profile ids in the preference chain, with the reason written into `bedrock.py` so nobody simplifies it back to a bare id. | Name the profile in the error: "this model is only available through an inference profile; try `us.<id>`". Bedrock already knows the answer at the moment it refuses. The current message sends the reader to the provisioned-throughput documentation, which is the wrong document. |
| 8 | Get a multimodal read of a carrier tracking page working. | Built four sample tracking pages as HTML, screenshotted them with Playwright at 2x, and sent the PNG bytes to `Converse` in an `image` content block with a forced `toolConfig`. | Some fiddling to get image bytes accepted, and a rough extraction to clean up afterwards. | Worked first time on all four, at high confidence, in 4 to 6 seconds each. It normalised the USPS number printed as `9400 1118 9922 3197 4284 90` into the unspaced form without being asked, read "Friday, September 20, 2026 at 2:11 P.M." into a date and a 24-hour time, and returned the printed string verbatim alongside. Forced tool use (`toolChoice: {"tool": ...}`) meant no JSON parsing of prose at any point. | None — recorded because it is the opposite of friction and the brief asks what worked | N/A | The Converse image block takes raw `bytes` rather than base64, which is the right call and easy to miss because the docs show base64 in several places. Worth one line: the SDK does the encoding. |
| 9 | Decide what "the camera saw nothing" is allowed to mean. | Wrote the reconciliation rule, then read the feature-depth note for this app. | A verdict rule, which I had. | The rule was wrong in a way I had not seen. An empty event log means either nobody came or nobody was watching, and the app had no way to tell them apart, so it would print "not consistent with camera" over an hour when the doorbell was unplugged. Ring publishes no connectivity or offline webhook, so there is no event to key on. | High. A design defect rather than a tool defect, but it cost a rebuild | Added `coverage.py`, which samples `GET /v1/devices/{id}/status` on a schedule through `status_poller.py` and treats only the span between two online samples less than 30 minutes apart as covered. A "not consistent" verdict over a window with any gap is downgraded to indeterminate with the gap printed. Every existing reconciliation test had to gain coverage samples, which is the correct outcome: a test that omitted them was testing the wrong rule. | Publish a device-connectivity webhook. Polling a status endpoint to find out whether a camera was recording is the kind of thing every integrator builds separately and most get wrong, and the ones who do not build it ship exactly the bug above. For a product that reconciles an absence against a camera, the difference between "saw nothing" and "was not watching" is the whole product. |
| 10 | Render a print-grade document to the typography spec, which names Charter, Public Sans and IBM Plex Mono and says to ship the font files rather than fetch them. | `fc-list` for each. | At least a usable open substitute installed. | Bitstream Charter is present, but only as TeX Type 1 `.pfb` files, which a browser cannot load. No woff2 anywhere on the machine, and no Public Sans or Plex Mono at all. | Low | Used the fallback stack the reference specifies (Georgia, Liberation Serif, DejaVu Sans Mono) and said so in `templates/record.css` and in the README, rather than naming fonts the pack does not ship. This is the exact failure the reference warns about, so hiding it would have been worse than having it. | N/A: our own constraint, recorded so the next person does not assume the fonts are there. |
| 11 | Work out how far back a newly-connected household's evidence can reach, since a delivery dispute is something a person goes looking for *after* a parcel goes missing. | Read the event-history endpoint's own description alongside the consent and authorisation flow. | History for the retention window, gated on the plan tier the way clip retrieval is (row 4). | Something narrower. Event history is gated to the moment consent was granted, and there is no backfill: the grant is the start of the record, not a key to an existing one. A household that installs this app on Tuesday because Monday's parcel never arrived has, for Monday, nothing. | High for the product, and the most consequential thing in this log after row 1, because it inverts the order the product is used in. Every delivery dispute begins with a missing parcel, and consent is granted after that. | None available; this one cannot be worked around, only disclosed. The app reconciles forward from the grant and `SPEC.md` now says plainly that it cannot speak to a delivery that predates its own install. The cost is that the first dispute a household brings to this product is the one dispute it can never answer, which is a real limit on the pitch rather than on the code. | Say it on the event-history page, in one sentence, next to the consent flow: history begins at the grant. It reads today as though consent unlocks access to a record that already exists, which is the reasonable assumption for a camera that has been recording for a year. And consider whether a household should be able to grant retrospective access to its own footage, because the data is theirs, the retention window has already paid for it, and the absence of that grant is the difference between a product that can answer a dispute and one that can only witness the next one. |
| 12 | Install and start the service from the documented path, after an audit flagged that nobody had done it from a clean tree. | Read `requirements.txt` and the README's install block, rather than running it: the audit that would have run it stopped before reaching this app. | The dependency list to be either complete or loudly incomplete. | `python-multipart` is in `requirements.txt` for `POST /read`, the tracking-page reader, and the file's own comment records what its absence does: FastAPI raises at import, before the server starts. So the failure is not a 500 on the one route that needs it, it is the whole application declining to boot, with a traceback pointing at form parsing rather than at the reader. **Stated honestly: we did not reproduce this.** `docs/CLEAN-RUN.md` records this app as never installed and never run from a clean tree, so the dependency is declared on the documented path and the import-time failure is the comment's claim, not our observation. | Unknown, and recorded as unknown. Low if the declared dependency is all that is needed; high if a fresh install finds anything else, because the symptom is a dead process rather than a degraded feature. | None yet. The honest state is that the documented install path looks right on paper and has never been walked. | Not Amazon's, and not a platform finding: it is ours, and it is the gap a judge is most likely to find before we do. The general lesson for anything FastAPI-shaped is that a form-parsing dependency fails at import rather than at the route, so "one optional feature is missing" and "the server will not start" look identical in a requirements file and completely different on a judge's machine. |

---

## Two findings from the end-of-build audit

Both were found by reading the artefact the product produces, not by running the suite.
The suite was green for both.

### The word `verbatim` is a promise, and it was printed over a string nothing checked

`tracking_reader.py` reads eight fields off one `Converse` tool call. Two of them go
through the guard:

```python
reading.status_text   = _apply_guard(reading, "status line", ..., _WITHHELD)
reading.location_note = _apply_guard(reading, "location note", ..., "")
```

Four from the same call do not: `tracking_number`, `carrier_name_printed`, `reference`
and `claimed_at_text`. The last of those is prose by its own schema description — "the
delivery date and time exactly as printed, character for character" — and `filed_record.py`
renders it like this:

```python
f' The page displayed this as <span class="verbatim">"{html.escape(claim.claimed_at_text)}"</span>;'
```

`class="verbatim"` is the strongest presentational claim this document makes. It tells
the reader these are the carrier's own printed words. It is applied to a model-authored
string with no check behind it.

The whole-page check exists — `guard_document.py` has it, and it would catch this. It is
called in exactly one place, the evidence pack. The filed record goes straight to the
browser and into the dispute pack, and neither is document-checked. The dispute pack is
the artefact that goes to the carrier and, if it gets that far, to an ombudsman.

The fix is two lines: `_apply_guard` on `claimed_at_text`, and wrap the filed record's
return in the document assertion. This is a common shape of bug: a hand-maintained list
of fields to guard, sitting next to a schema that grew new ones, is a list that goes
stale on the next commit. Walk the parsed object instead, and reject the record on any
field that fails, including the ones nothing renders today.

**Feedback for Bedrock, since this is where it lands.** `toolConfig` gives you a JSON
schema, and a JSON schema constrains shape and never content. There is no way to express
"this string must be a span of the image or document I gave you", which is the single
constraint that would make grounded extraction safe by construction. Every developer
building this shape writes the same verifier, and the ones who forget one field ship the
defect above. A documented pattern for source-grounded extraction in the Bedrock guides,
or a decoding constraint if one is possible, would close a class of bug that is currently
everybody's homework. Our prompt for this field said "character for character" and the
model complied — the point is that compliance was not checkable.

### The guard is good and nothing proves it

`guard_rules.py` holds twelve regexes, several of them intricate. Ported out and run
against sentences written to get past them:

```
BLOCKED -> The driver never came to the door.
BLOCKED -> UPS falsified the delivery scan.
BLOCKED -> Nobody attempted delivery at this address.
clean   -> The courier marked it delivered without attending the address.
```

Three of four caught, which held up better than most hand-written denylists of this
kind. And it has no adversarial test at all. The only guard assertion in the suite is
`assert guard.is_clean(visible_text(html))` over a page assembled from fixed literals,
which passes with `RULES` emptied. Twelve regexes have never been shown a string they
match.

That is worth reporting as friction rather than as a confession, because it is a specific
shape of testing mistake: proving a guard is *correct* in isolation and never proving it
is *applied*, or proving it is applied and never showing it a hostile input. A suite can
be green on both counts and the guard can be dead code. The cheap fix is one shared
adversarial corpus that does not come from the denylist, run against every guard in the
project, so nobody writes a test whose input was derived from the rule it is meant to
test.

---

## Product feedback answers

**Tools, APIs and SDKs used.** Ring's REST API reference and webhook documentation,
read-only; no official Ring SDK exists. Amazon Bedrock through `boto3` Converse, for
multimodal reading of a carrier tracking page with forced tool use, and for the claim
letter. Playwright to screenshot the sample pages. Python standard library plus pytest.

**Onboarding, zero to hello world.** Bedrock: minutes. Credentials already resolved,
one CLI call to check a model id, then the SDK, and the first multimodal extraction
worked on the first attempt. Ring: never reached. There is no hello world available to a
developer without a subscribed US device, and that is the single largest friction point
on this track.

**What worked.** Converse's image content block taking raw bytes, and `toolChoice`
forcing a tool call so there is no prose to parse. Ring's JSON:API envelope and the
webhook event vocabulary, which are consistent and easy to reproduce for replay. The
rate-limit headers are documented.

**What needs work.** No sandbox, despite the word appearing in Ring's own glossary and
FAQ and despite the hackathon page implying one. No worked webhook-signing example and no
named replay-protection header. No device-connectivity webhook, so "the camera saw
nothing" and "the camera was not watching" are indistinguishable without a polling
harness every integrator writes separately. Clip retrieval plan-gated in a footnote, with
a `416` as the symptom. Event history that begins at the consent grant with no backfill,
which for a disputes product means the dispute that sent someone looking for the app is
the one it cannot answer (row 11). On the AWS side: `ListFoundationModels` listing models the
account cannot invoke, error messages that name the wrong document, and no way to
constrain a model string to a span of its source.

**Amazon Devices Builder Tools.** Not used. It is the first thing listed under "Start
here" for this track and we went straight to the API reference. What would have made us
install it: a concrete claim about what it can answer. The two questions we actually had
were "what exactly does Ring hash for the signature" and "is this endpoint plan-gated",
and neither is answerable from the reference, so if the Builder Tools know either of
them that is worth saying on the page.

**Would we build with it again?** Yes for the Bedrock half without hesitation; the
multimodal extraction is the best thing in this build and took an afternoon. For Ring,
yes for the API shape and no for the onboarding, which we could not complete and which
forced the entire product to be demonstrated on replayed fixtures.

## One thing we would tell the next team

Check what your own document claims about itself. Ours printed a model's string inside a
span called `verbatim`, on the page that goes to the carrier. Nothing was lying on
purpose; the guard list had been written before the schema grew, and the strongest
typographic claim in the document ended up over the one field nobody had checked.
