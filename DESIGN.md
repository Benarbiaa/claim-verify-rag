---
name: claim-verify-rag UI
description: The run as an assay plate. Claims are the rows, sources the columns, and the pipeline sits on one time axis.
colors:
  paper: "#f4f5f3"
  sheet: "#ffffff"
  sheet-sunk: "#eceeeb"
  ink: "#15181c"
  ink-2: "#454b53"
  ink-3: "#636a73"
  rule: "#dcdfe2"
  rule-strong: "#b9bec5"
  supported: "#0072b2"
  supported-ink: "#005a8c"
  supported-wash: "#e3eff7"
  contradicted: "#d55e00"
  contradicted-ink: "#a84a00"
  contradicted-wash: "#fbeadf"
  unverifiable: "#8a9099"
  unverifiable-ink: "#545b64"
  error: "#e69f00"
  error-ink: "#855b00"
  error-wash: "#fbf1d9"
  dark-paper: "#0f1216"
  dark-sheet: "#161a1f"
  dark-ink: "#e9ebee"
  dark-supported: "#56b4e9"
  dark-contradicted: "#ef7a2e"
  dark-error: "#f0b429"
typography:
  question:
    fontFamily: "Atkinson Hyperlegible Next, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(1.25rem, 0.95rem + 0.95vw, 1.9rem)"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  panel-title:
    fontFamily: "Atkinson Hyperlegible Next, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 800
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Atkinson Hyperlegible Next, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.625
  figures:
    fontFamily: "Atkinson Hyperlegible Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.01em"
rounded:
  cell: "6px"
  control: "8px"
  sheet: "8px"
  primary: "8px"
  well: "9999px"
spacing:
  gutter: "24px"
  gutter-mobile: "16px"
  panel-gap: "24px"
  row: "8px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.primary}"
    height: "40px"
    padding: "0 16px"
  segmented-control:
    backgroundColor: "{colors.sheet-sunk}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.control}"
    padding: "2px"
  segmented-control-active:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.sheet}"
    padding: "20px"
  plate-cell:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.well}"
    size: "32px"
  citation-chip:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-2}"
    rounded: "5px"
    padding: "1px 6px"
---

# Design system: claim-verify-rag UI

The pipeline's architecture is documented in [`docs/design.md`](docs/design.md). This file covers only the web UI's look.

## Overview

**Creative North Star: "The assay plate."** Each answer is treated like a lab sample. Every claim is tested against every source, and the result reads like a lab test plate being filled in.

The page is a lab result sheet: cool paper, ink, hairline rules, and figures set in a monospace face. The verdicts are the only colour on the page. The UI is used in two situations: as a demo on a projector in a lit room or on a laptop across a table, and as an inspection tool for technical viewers. It has to read in five seconds and still hold up when someone looks closely.

**Key characteristics:**
- The plate (claims × sources) is the signature component. Each cell is a well that says what one source did with one claim.
- One time axis for the whole run. Every duration is drawn to scale, and rate-limit waits are hatched.
- Something that hasn't happened yet is shown hatched, not with a spinner.
- Evidence has a side: sources *for* a claim sit on the left, sources *against* on the right, everywhere.
- Light theme for projectors, dark theme for laptops. It follows the system until the viewer picks one.

## Colors

The strategy is restrained: neutrals, plus a fixed palette of verdict colours taken from Okabe-Ito, a colour set designed to stay distinguishable for colour-blind viewers. Colour is never used alone. Every verdict also has a shape and a label.

### Primary
- **Supported blue** (`#0072B2`, dark `#56B4E9`): a filled circle, and sources that support a claim.
- **Contradicted vermillion** (`#D55E00`, dark `#EF7A2E`): a filled circle with a cross, and sources that contradict a claim (drawn as diamonds in the plate).

### Secondary
- **Error amber** (`#E69F00`, dark `#F0B429`): only for `error`, a hatched square. It is never used for warnings or flags.
- **Unverifiable grey** (`#8A9099`): an empty ring with a question mark.

### Neutral
- **Paper** `#F4F5F3` is the page. **Sheet** `#FFFFFF` is used for tables and panels. **Sunk** `#ECEEEB` is used for selected rows, passages and controls.
- **Ink** `#15181C`, **Ink-2** `#454B53` (secondary text), **Ink-3** `#636A73` (captions, 4.8:1 contrast on white).
- **Rule** `#DCDFE2` and **Rule-strong** `#B9BEC5` for hairlines and dashed outlines.

### Named rules
**The verdict-only rule.** Colour belongs to verdicts. UI chrome, stages and buttons stay ink and grey. A flag that isn't a verdict (for example, "the judge relied on other sources") is written in ink, not in a verdict colour.

**The contested rule.** Contested is not a colour of its own. It is the supported and contradicted colours together: a circle split diagonally.

**The text-ink rule.** Verdict fills are too light for small text on white. Text uses the `-ink` variants.

## Typography

**Body and display:** Atkinson Hyperlegible Next, a font built to stay readable for people with low vision, which suits a room with a projector.
**Figures:** Atkinson Hyperlegible Mono, used only for measurements: seconds, tokens, scores, IDs and file names.

The root size scales with the viewport, from 15 px at 1280 px wide to 18 px at 1920 px.

### Hierarchy
- **Question** (800, clamp 1.25–1.9 rem, tracking −0.025em): the sample's label, the only large text.
- **Panel title** (800, 1.25 rem): one per focused stage.
- **Section heading** (700–800, 1 rem).
- **Body** (400, 0.875–1.05 rem, line-height 1.6–1.7): justifications, passages and the draft, capped at about 70 characters per line.
- **Figures** (mono 0.7–0.75 rem, tabular numerals): step figures, axis ticks, scores.

### Named rules
**The measurement rule.** Monospace means the text is a measurement or an identifier. It is never used just to look technical.

**No eyebrows.** Headings stand on their own, with no small upper-case labels above them.

## Layout

The page has a 1760 px maximum width, with 24 px gutters (16 px on mobile). An answering run reads from top to bottom:
1. The question and the run details.
2. The transport controls (play, speed, scrubber), the stage steps, and the time axis. This block sticks to the top only on screens at least 860 px tall and 1024 px wide.
3. The focused stage's output: one panel at a time.

On wide screens the plate and the claim detail sit side by side (about 1.35 : 1), and the detail stays in view while the plate scrolls. Tables scroll inside their frame on narrow screens; the page itself never scrolls sideways.

## Elevation & Depth

The design is flat and uses hairlines. The only shadow is `--shadow-lift`, a soft shadow with an offset, used on primary buttons, tooltips and the scrubber handle. Panels and tables use a 1 px rule border and no shadow.

## Shapes

- **Wells** are round: verdict marks and plate cells.
- **Squares** mean "no conclusion": the `error` mark, and the frame around the cell the draft cited.
- Controls and sheets have an 8 px corner radius; passages and cells have 6 px.

## Components

### Plate (signature)
A table with claims as rows and source documents as columns (sorted by relevance). Each row starts with the claim's verdict well, then the claim text and "draft cited *X*". Each cell is a 32 px well:

| Cell mark | Meaning |
|---|---|
| blue circle | the source supports the claim |
| vermillion diamond | the source contradicts the claim |
| small grey ring | the judge read it; it says nothing about the claim |
| dash | not retrieved for this claim |
| hatched | not judged yet |

A square frame marks the source the draft cited. Selecting a row opens the claim detail: the verdict, the judge's reasoning, For | Against columns of evidence passages, and the silent passages, folded.

### Time axis (signature)
Pipeline steps sit above the axis. The axis is a 20 px track: work is drawn solid in ink-2, waits are hatched, and ghost segments show what is still to come. A vertical needle marks the current position. Verdict marks drop onto the axis at the moment each verdict was given, and a single leader line joins the focused step to its part of the axis.

### Buttons
- **Primary:** an ink fill with sheet-coloured text, 40 px tall (48 px on the intro), shrinks to 97% on press.
- **Segmented controls** (speed, filters): a sunk track with the active item raised on a sheet background.

### Citation chip
Inline in the draft: the short name of the source and `#chunk`. When selected, it turns supported-wash with a supported border, and the matching passage is highlighted in the side list.

### Passage
A sunk block showing the document's short name, the chunk number and a score bar (fixed scale from 0.5 to 1). The text is clamped to 3–5 lines and can be expanded.

## Do's and Don'ts

**Do**
- Pair every verdict colour with its shape and its label.
- Draw durations to scale on the shared axis, waits included.
- Show pending states as hatched.
- Keep supporting sources on the left and contradicting sources on the right.
- Keep motion short: under 300 ms, a strong ease-out, and a spring only for the landing of a verdict well. Nothing moves when reduced motion is on.

**Don't**
- Don't use the error amber for anything but `error`.
- Don't add cards with icons and headings, stat tiles, or gradients.
- Don't put small upper-case labels above headings.
- Don't use monospace for prose.
- Don't use colour without a shape.
- Don't hide rate-limit waits or retries: showing them honestly is part of the product.
