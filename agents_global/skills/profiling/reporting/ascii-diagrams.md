# ASCII A/B diagrams

A results table says how much an A/B changed. A diagram says what is different between the arms, which is
what a reader learning the system needs. Draw one for every A/B whose mechanism you can state.

## Where it goes

- **Chat: always, once.** Show the diagram the first time you report an A/B result, next to the table.
  Don't repeat it in later replies unless the mechanism changes.
- **PR descriptions and write-ups: case by case.** Include it when the mechanism is in the weeds and merits
  explanation. Leave it out when the change is well known (a fused op, a larger tile). A PNG figure
  (`reporting/figures.md`) can replace it when the mechanism is visual in a real trace.

## Pick the form by what differs

Most A/B differences are about structure: who holds what, what moves where, what runs where, what depends
on what. Start there. Draw a timeline only when the difference is when things happen.

| What differs between the arms | Form |
|---|---|
| Where data lives or how it is laid out (sharding, replication, memory layout, cache residency) | structure |
| What moves where, and how much (collectives, host-device copies, loads into shared memory) | structure |
| Which unit does the work (host versus GPU, which kernel, which rank or warp role, fused or not) | structure |
| How work maps to resources (CTAs to queries, experts to ranks, requests to replicas) | structure |
| Ordering, overlap, waiting and critical paths | timeline |

When a change has both, draw the structure first and add a timeline only if the ordering is the point.

## Rules for both forms

- **One diagram per A/B, at most 100 columns,** in a fenced code block, arm A first and arm B second (side by
  side when both fit, else stacked).
- **The same frame for both arms:** the same boxes, actors and labels in the same places, so the eye finds the
  difference rather than the redrawing.
- **Mark only the difference.** Draw what is needed to see the change and collapse the rest (`...`). Point at
  what changed with `^` lines or a `<-- changed` note.
- **Say whether quantities are measured.** Sizes, counts and times in the diagram either come from the
  results (and match the table) or the first line says "schematic".
- **One sentence underneath** states the mechanism and how it is known: measured, inferred, or hypothesis.
- **Optionally, a refuted alternative.** A plausible explanation that was tested and failed teaches as much
  as the winning arm. One line or a third panel.

## Structure form

Boxes are units that hold data or do work (GPU, rank, SM, CTA, host, buffer). Arrows are movement or
dependency, labeled with what moves and how much. Keep arrows going one way (left to right or top to
bottom) where possible.

Example, the grid shape of the DSv4 CuTe forward (`tools/intra-kernel.md`), with measured numbers:

```
A: non-persistent, one CTA per query (16384 CTAs, 124 per SM, one after the other)

 queries  q0     q1     q2    ...  q16383
          |      |      |            |
          v      v      v            v
 CTAs    [c0]   [c1]   [c2]   ... [c16383]     each CTA loads its own Q cold, then waits for it

B: persistent, one CTA per SM looping over queries (132 CTAs)

 queries  q0 q132 q264 ...   q1 q133 q265 ...   ...   q131 q263 ...
           \   |   /          \   |   /                  \   |
            v  v  v            v  v  v                    v  v
 CTAs       [ c0 ]             [ c1 ]          ...       [ c131 ]
                 next query's Q loads during this query's epilogue
                 ^ changed: Q latency moves off the critical path
```

Measured with IKET traces: in the persistent grid the next query's Q lands 2.3 µs after issue, inside the
2.4 µs epilogue, so its latency stops mattering. In the non-persistent grid every CTA waits for its own Q.

A schematic systems example, of where an expert's tokens travel under two dispatch schemes:

```
schematic

A: all-to-all dispatch                              B: all-gather tokens, compute local experts
 rank0 --tokens for e4..e7--> rank1                 rank0 <--all tokens--> rank1
 rank1 --tokens for e0..e3--> rank0                   |                      |
   |                            |                     v                      v
 [experts e0..e3]           [experts e4..e7]        [e0..e3 on all tokens]   [e4..e7 on all tokens]
   |                            |                     |                      |
 rank0 <--results back------- rank1                 reduce-scatter outputs <-- changed: bytes moved
```

## Timeline form

Use one row per actor (warp role, stream, rank, process), both arms anchored at the same event at column 0
on a shared time axis.

- The first line says "to scale, 1 char = X µs" with measured medians, or "schematic, order only". Never mix.
- Glyphs: `>` issue, `=` work, `.` waiting or idle, `|` completion or sync point. Label runs inline.

Example, the tile-count fix in the same kernel:

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
