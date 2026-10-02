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
  stage-1: "oklch(0.5 0.09 195)"
  stage-2: "oklch(0.5 0.12 145)"
  stage-3: "oklch(0.49 0.16 295)"
  stage-4: "oklch(0.5 0.17 345)"
  dark-stage-1: "oklch(0.76 0.1 195)"
  dark-stage-2: "oklch(0.76 0.13 145)"
  dark-stage-3: "oklch(0.74 0.12 295)"
  dark-stage-4: "oklch(0.74 0.14 345)"
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
    fontFamily: "Atkinson Hyperlegible Next, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
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

The page is a lab result sheet: cool paper, ink, hairline rules, and figures set in a monospace face. Colour has two jobs only: verdicts, and telling the pipeline steps apart. The UI is used in two situations: as a demo on a projector in a lit room or on a laptop across a table, and as an inspection tool for technical viewers. It has to read in five seconds and still hold up when someone looks closely.

**Key characteristics:**
- The plate (claims × sources) is the signature component. Each cell is a well that says what one source did with one claim.
- One time axis for the whole run. Every duration is drawn to scale, and rate-limit waits are hatched.
- Something that hasn't happened yet is shown hatched, not with a spinner.
- Evidence has a side: sources *for* a claim sit on the left, sources *against* on the right, everywhere.
- Light theme for projectors, dark theme for laptops. It follows the system until the viewer picks one.

## Colors

The strategy is restrained: neutrals, a fixed palette of verdict colours taken from Okabe-Ito (a colour set designed to stay distinguishable for colour-blind viewers), and four step colours. Colour is never used alone. Every verdict also has a shape and a label, and every step its number and name.

### Primary
- **Supported blue** (`#0072B2`, dark `#56B4E9`): a filled circle, and sources that support a claim.
- **Contradicted vermillion** (`#D55E00`, dark `#EF7A2E`): a filled circle with a cross, and sources that contradict a claim (drawn as diamonds in the plate).

### Secondary
- **Error amber** (`#E69F00`, dark `#F0B429`): only for `error`, a hatched square. It is never used for warnings or flags.
- **Unverifiable grey** (`#8A9099`): an empty ring with a question mark.

### Steps
One colour per pipeline step, in hues kept away from the verdicts' blue, vermillion and amber. The indexing steps reuse them in order (Load, Cut, Embed, Store); Clean shares Load's teal, as both prepare the text.
- **1 · Search** teal `oklch(0.5 0.09 195)`
- **2 · Answer** green `oklch(0.5 0.12 145)`
- **3 · Split** violet `oklch(0.49 0.16 295)`
- **4 · Check** magenta `oklch(0.5 0.17 345)`
- **Summary** stays ink.

Dark theme: the same hues, lighter (lightness 0.74–0.76).

### Neutral
- **Paper** `#F4F5F3` is the page. **Sheet** `#FFFFFF` is used for tables and panels. **Sunk** `#ECEEEB` is used for selected rows, passages and controls.
- **Ink** `#15181C`, **Ink-2** `#454B53` (secondary text), **Ink-3** `#636A73` (captions, 4.8:1 contrast on white).
- **Rule** `#DCDFE2` and **Rule-strong** `#B9BEC5` for hairlines and dashed outlines.

### Named rules
**The two-jobs rule.** Colour belongs to verdicts and to pipeline steps. UI chrome and buttons stay ink and grey. Step colours mark where a step appears (its button, its time on the axis, its panel's number badge) and never fill a well: wells are verdicts. A flag that isn't a verdict (for example, "the judge relied on other sources") is written in ink, not in a verdict colour.

**The contested rule.** Contested is not a colour of its own. It is the supported and contradicted colours together: a circle split diagonally.

**The text-ink rule.** Verdict fills are too light for small text on white. Text uses the `-ink` variants.

## Typography

**Body and display:** Atkinson Hyperlegible Next, a font built to stay readable for people with low vision, which suits a room with a projector.
**Figures:** the same face with tabular numbers. Monospace (Atkinson Hyperlegible Mono) appears only in the "Technical details" dump.

The root size scales with the viewport, from 15 px at 1280 px wide to 18 px at 1920 px.

### Hierarchy
- **Question** (800, clamp 1.25–1.9 rem, tracking −0.025em): the sample's label, the only large text.
- **Panel title** (800, 1.25 rem): one per focused stage.
- **Section heading** (700–800, 1 rem).
- **Body** (400, 0.875–1.05 rem, line-height 1.6–1.7): justifications, passages and the draft, capped at about 70 characters per line.
- **Figures** (0.75 rem, tabular numerals): step counts, times.

### Named rules
**The one-line rule.** A panel has a title that says what it is for, and at most one line of explanation. Anything longer (the judge's reasoning, a passage) is clamped and opens on click.

**Plain words.** Steps are named Search, Answer, Split, Check and Summary. Panel titles carry the same step number.

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

### Fact-check grid (signature)
A table with claims as rows and source documents as columns (sorted by relevance). Each row starts with the claim's verdict well, then the claim text. Each cell is a 28 px empty well that may hold one mark:

| Cell | Meaning |
|---|---|
| blue dot | the source supports the claim |
| vermillion diamond | the source contradicts the claim |
| empty | the source says nothing about it |
| hatched | not checked yet |

Selecting a row shows the claim card: the verdict, the claim, the reasoning (three lines, "Read more"), and For | Against lists of sources; clicking a source opens its passage.

### Time axis (signature)
Five numbered step buttons (name + one count), each topped by a 3 px bar of its step colour, sit above a 12 px bar: working is solid in the step's colour, waiting is hatched in the step's colour, what is still to come is ghosted, and a needle marks the current position. One line above the bar gives the total time, the share spent waiting, and a two-item legend.

### Buttons
- **Primary:** an ink fill with sheet-coloured text, 40 px tall (48 px on the intro), shrinks to 97% on press.
- **Segmented controls** (speed, filters): a sunk track with the active item raised on a sheet background.

### Source tag
Inline in the answer: the source's short name. Clicking it shows that passage in the side column.

### Passage
A sunk block with the passage text, clamped to a few lines; clicking it expands it.

## Do's and Don'ts

**Do**
- Pair every verdict colour with its shape and its label.
- Draw durations to scale on the shared bar, waits included.
- Keep one title and at most one line of explanation per panel.
- Show pending states as hatched.
- Keep supporting sources on the left and contradicting sources on the right.
- Keep motion short: under 300 ms, a strong ease-out, and a spring only for the landing of a verdict well. Nothing moves when reduced motion is on.

**Don't**
- Don't use the error amber for anything but `error`.
- Don't put a step colour inside a well or on a verdict.
- Don't add cards with icons and headings, stat tiles, or gradients.
- Don't put small upper-case labels above headings.
- Don't use monospace for prose.
- Don't use colour without a shape.
- Don't hide rate-limit waits or retries: showing them honestly is part of the product.
