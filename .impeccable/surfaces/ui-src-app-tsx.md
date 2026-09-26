---
version: 1
slug: "ui-src-app-tsx"
primary_target: "ui/src/App.tsx"
related_targets: ["ui"]
---

# Surface: claim-verify-rag web UI (ui/)

Scope: the whole UI (runs register, answering run view with replay and live modes, indexing run view).
Visitor mode: Operate, doubling as a live demo for recruiters and a jury (projector in a lit room, or laptop).
Audience/job: understand in seconds that the system drafts an answer, splits it into claims and re-checks each
claim against every source; technical viewers inspect passages, evidence, tokens, retries, waits.
Constraints: English UI; light + dark themes with toggle; no pipeline logic in the UI; never trigger LLM calls
without explicit user action and a visible cost estimate.

## Direction contract

THESIS: Each answer is a specimen assayed against every source; the run reads as an assay plate (claims x sources)
filling in cell by cell, not as an ML-ops dashboard of cards, tabs and stat tiles.

OWN-WORLD: Analytical-lab result sheet. Cool white report paper (dark: instrument slate), ink text, hairline rules,
Atkinson Hyperlegible + Atkinson Hyperlegible Mono for figures. Colour is reserved for verdicts (Okabe-Ito):
supported blue filled well, contradicted vermillion well with cross, contested well split diagonally blue/vermillion,
unverifiable hollow grey ring, error hatched amber square. Support always left, contradiction always right.
Pending = half-density hatch. One shared time axis for every duration; rate-limit waits hatched to scale.

STORY: The visitor reads the question, presses play, watches retrieval, draft and claims appear, then sees the plate
fill row by row; they learn every source was consulted and where sources agree, disagree or are silent, and that
most of the run's time was waiting on rate limits.

FIRST VIEWPORT: Top: question as specimen label with run meta and the transport (play/pause/step/speed/scrubber).
Below: full-width run time axis (Retrieve | Draft | Decompose | Verify with waits hatched). Main: the plate
(left ~60%) and claim detail panel (right) with for/against sides and evidence. Primary action: Play.

FORM: Assay Plate Report, candidate 6 of 7 in my grounded list; seed key 3274b8a9. Signature interaction: verdict
wells landing into the plate as cue events replay, with the time axis cursor advancing on one graticule.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
