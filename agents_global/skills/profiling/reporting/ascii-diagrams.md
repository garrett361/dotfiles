# ASCII A/B diagrams

A results table says how much an A/B changed. A diagram says what is different between the arms, which is
what a reader learning the system needs. Draw one for every A/B whose mechanism you can state.

## Where it goes

- **Chat: always, once.** Show the diagram the first time you report an A/B result, next to the table.
  Don't repeat it in later replies unless the mechanism changes.
- **PR descriptions and write-ups: case by case.** Include it when the mechanism is in the weeds and merits
  explanation (a dependency between two loads, a reordering inside a kernel). Leave it out when the change
  is well known (a fused op, a larger tile). A PNG figure (`reporting/figures.md`) can replace it when the
  mechanism is visual in a real trace.

## Rules

- **One diagram per A/B, at most 100 columns,** in a fenced code block. Arm A sits above arm B on one shared
  time axis, with one row per actor (warp role, stream, rank, process). Both arms are anchored at the same
  event, at column 0.
- **Say whether it is drawn to scale.** The diagram's first line says either "to scale, 1 char = X µs",
  with medians from the measurement, or "schematic, order only". Never mix the two in one diagram.
- **One glyph set.** Use `>` for an issue, `=` for work, `.` for waiting or idle, and `|` for a completion or
  sync point. Label runs inline (`wait Q`, `GEMM`). Arrows or `^` lines underneath point at what changed.
- **Mark only the difference.** Draw the rows and spans needed to see the change, and collapse everything
  else (`...`).
- **Numbers come from the results.** Every number in the diagram matches the results table or the trace
  intervals.
- **One sentence underneath** states the mechanism and how it is known: measured, inferred, or hypothesis.
- **Optionally, a refuted alternative.** When a plausible explanation was tested and failed, a third panel
  or a single line saying so teaches as much as the winning arm.

## Example

From the DSv4 CuTe forward study (`tools/intra-kernel.md`):

```
NP TMA forward, one CTA, sliding16k (to scale, 1 char = 0.1 µs, medians)

np_tma (8.67 µs/CTA)
  warp 0     >Q..................wait Q.....|GEMM ...
  producer   tile count.......|gather........
             ^ 4-byte load arrives late (0.83 µs): the 64 KiB TMA is in flight

np_tma_tcfirst (7.58 µs/CTA)
  warp 0     tc...|>Q.......wait Q....|GEMM ...
  producer   tc...|gather....
                  ^ wait for the tile count, then issue Q: Q lands 0.42 µs sooner
```

Measured with IKET traces and timed untraced: waiting for the tile count before the Q TMA recovers 86 of
the 97 µs that TMA cost. Issuing the load first without waiting (`np_tma_tcload`) did not help.
