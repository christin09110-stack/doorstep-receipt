# Where Doorstep Receipt's typefaces come from

This app's screen UI was redesigned to follow Callsheet's design language.
Callsheet names two faces and no others: Montserrat for
every heading, label and line of prose, IBM Plex Mono for anything that is a
machine record — a timestamp, an event ID, a digest, a tracking number. This
app previously vendored Lora, a serif, for "what a person wrote" against a
mono face for "a machine record." That split by kind-of-content was real and
is kept — the digest, the event log and every timestamp are still `--mono` —
but Callsheet has no serif register at all, and the brief is to reproduce its
type system rather than keep a third one running alongside it. Lora is
removed; nothing in this app now names Iowan Old Style, Palatino or Georgia.

| In the app | File | Weight | Style | Licence | Source |
| --- | --- | --- | --- | --- | --- |
| `static/fonts/Montserrat-400.woff2` | Montserrat | 400 | Normal | SIL Open Font License 1.1 | [Google Fonts: Montserrat](https://fonts.google.com/specimen/Montserrat) |
| `static/fonts/Montserrat-600.woff2` | Montserrat | 600 | Normal | SIL Open Font License 1.1 | [Google Fonts: Montserrat](https://fonts.google.com/specimen/Montserrat) |
| `static/fonts/Montserrat-700.woff2` | Montserrat | 700 | Normal | SIL Open Font License 1.1 | [Google Fonts: Montserrat](https://fonts.google.com/specimen/Montserrat) |
| `static/fonts/IBMPlexMono-400.woff2` | IBM Plex Mono | 400 | Normal | SIL Open Font License 1.1 | [Google Fonts: IBM Plex Mono](https://fonts.google.com/specimen/IBM+Plex+Mono) |
| `static/fonts/IBMPlexMono-700.woff2` | IBM Plex Mono | 700 | Normal | SIL Open Font License 1.1 | [Google Fonts: IBM Plex Mono](https://fonts.google.com/specimen/IBM+Plex+Mono) |

These are the same weights Callsheet itself loads
(`family=Montserrat:wght@400;600;700&family=IBM+Plex+Mono:wght@400;700`), but
fetched as files rather than left as a `fonts.googleapis.com` `<link>`: this
app already vendors its faces for the same reason a claims pack that leaves
this app and a browser rendering it should be the same document, with no
network call standing between them, and that reasoning didn't change when
the face did. Each file is the Latin-subset
`woff2` Google Fonts itself serves (fetched directly from `fonts.gstatic.com`,
same `unicode-range` Google's own CSS ships for the "latin" subset) and is
committed into this app, served from its own `/static` mount
(`doorstep_receipt/app.py`, `StaticFiles(directory=STATIC_DIR)`).

No italic weight is vendored for either face: nothing in this app's screen UI
sets `font-style: italic` on `--sans` or `--mono`.

The SIL Open Font License permits embedding, redistribution and modification;
the full licence text is at <https://openfontlicense.org/>. Nothing in either
file was altered beyond subsetting to the Latin range Google Fonts itself
already subsets to.

`--sans` in `templates/_shell.html` still lists a system fallback chain after
Montserrat (`-apple-system, "Segoe UI", Roboto, sans-serif`), and `--mono`
still falls back after IBM Plex Mono (`ui-monospace, Menlo, monospace`) — the
same fallback discipline the Lora stack used, now backed by a real file for
the first name in each list rather than a name with no file behind it.

## A second, separate font stack this redesign did not touch

`templates/record.css` — the stylesheet for the filed record handed to a
carrier, a different document from the screen UI `_shell.html` governs — has
its own `--face-text`/`--face-label`/`--face-data` stack and ships no font
file. That stylesheet is deliberately pure black on white because it is a
document meant for paper, and the redesign brief is explicit that it does not
take Callsheet's palette or type. Left exactly as found; its own header
comment already states the tradeoff.
