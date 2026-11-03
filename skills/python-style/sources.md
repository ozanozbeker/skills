# Sources

The rationale behind each rule in [`SKILL.md`](SKILL.md), condensed from the documents TIGER_STYLE.md links.
Read a section here when a rule needs defending, or when a case the rule does not cover needs the principle behind it.

## TIGER_STYLE.md

[TigerBeetle, Apache-2.0](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md).

**Style is design.**
The design goals are safety, performance and developer experience, in that order.
Readability is a means to those ends, never the end.
Style is only needed where understanding is missing (Let Over Lambda, below).

**Simplicity is the hardest revision, not the first attempt.**
Spend the thinking up front.
An hour or a day of design is worth weeks in production, because the cost of design is dwarfed by implementation, then by testing, then by operation.

**Zero technical debt.**
A problem solved in production costs many times a problem solved in design.
When a showstopper is found, solve it then.
The second attempt may never come, and shipped work that meets the goals is the only steady progress.

**Assertions downgrade a correctness bug into a liveness bug.**
A programmer error is unexpected and the only correct response is to crash.
An operating error is expected and must be handled.
Assertions multiply what a fuzzer can find.
A fuzzer proves only the presence of bugs, so build the mental model first, encode it as assertions, explain it in comments for the reviewer, and use the fuzzer last.

**Mechanical sympathy.**
Think about performance in the design phase, where the 1000x wins live and where profiling cannot yet run.
Sketch the four resources (network, disk, memory, CPU) on bandwidth and latency.
Faster resources are used more often, so weight by frequency: a memory cache miss repeated enough times costs a disk fsync.

**Naming.**
A great name captures what a thing is or does and shows understanding of the domain.
Units last, descending significance, so related names sort and line up.
A noun composes into documentation and derived names where a participle must be rephrased.
Overloading a term the domain already uses caused real confusion: "two-phase commit transfers" collided with the consensus protocol's two-phase commit, and became "pending transfers".

**Cache invalidation.**
Most bugs are a semantic gap in time or space.
Keep the check next to the use (POCPOU, place-of-check to place-of-use, a cousin of TOCTOU).
Keep one reference to state.
Shrink scope.
Prefer the simpler return type because dimensionality at the call site is viral through the call chain.

**Dependencies and tooling.**
A dependency carries supply-chain, safety and performance risk, and slow installs, amplified for infrastructure.
A tool carries a manual.
The right tool is often the one already in use (Carmack).
Standardizing on one language for scripts reduces dimensionality as the team and its range of tastes grow.

## NASA Power of Ten

Holzmann, [The Power of Ten: Rules for Developing Safety Critical Code](https://spinroot.com/gerard/pdf/P10.pdf), JPL.

Most coding guidelines hold over a hundred rules, many from personal preference, and rarely allow a tool to check compliance, so developers ignore them.
A small set of strict, mechanically checkable rules beats a large set of guidelines.
The ten:

1. Simple control flow: no `goto`, no `setjmp`/`longjmp`, no recursion.
   An acyclic call graph lets a tool prove that bounded executions are bounded.
2. Every loop has a fixed upper bound a tool can prove statically.
   A loop meant never to end carries the reverse proof.
3. No dynamic allocation after initialization.
   Allocators behave unpredictably, and use-after-free, leaks and overruns all vanish when memory is fixed.
4. A function fits on one printed page, about 60 lines, so it is a unit a reader can verify as a unit.
5. Two assertions per function on average, side-effect free, with a recovery action when one fails.
   Unit tests find a defect per 10 to 100 lines, so the odds of catching one rise with density.
   An assertion a tool can prove always true or always false does not count.
6. Declare data at the smallest scope.
   A value out of scope cannot be read or corrupted, and fewer assignment sites make a bad value easier to trace.
7. Check every non-void return value, and validate every parameter inside the function.
   The most violated rule.
   Ignoring a return value is allowed only with an explicit cast to `(void)` and, in doubtful cases, a comment.
   Keeping the rule means exceptions must be justified.
8. Limit the preprocessor.
   Ten conditional-compilation flags give up to 1024 versions of the code to test.
9. Restrict pointers to one level of dereference, and no function pointers, because they stop a static analyzer from proving control flow.
10. Compile with all warnings at the most pedantic setting from day one, with zero warnings, and run at least one static analyzer daily with zero warnings.
    A warning assumed invalid often turns out valid for a less obvious reason, so rewrite the code until the tool agrees.

The rules are a seat belt: uncomfortable at first, then unimaginable to skip.

The Python mapping: rules 1, 2, 4, 5, 6 and 7 apply as written.
Rule 3 becomes "build resources at startup and pass them in".
Rules 8 and 9 have no Python counterpart.
Rule 10 is ruff at `select = ["ALL"]`, a strict type checker, and pytest with warnings as errors.

## Abstractions are never zero cost

Freund, [Zig vs Rust: waylock](https://isaacfreund.com/blog/2022-05/).

A rewrite of the same program from Rust to Zig shrank a stripped release build from about 1.7 MiB to 69 KiB with safety checks on.
Removing a feature from the Rust build barely moved the number, so the size came from abstraction and from 48 crates the author had never read.
The cost of an abstraction is paid in size and in unaudited code even when runtime speed is unchanged.
In Python the same costs are install size, import time, lock churn, and code in the lock file nobody on the team has read.

## Push ifs up and fors down

matklad, [Push Ifs Up And Fors Down](https://matklad.github.io/2023/11/15/push-ifs-up-and-fors-down.html).

**Push ifs up.**
A function that checks for `None` and returns early hides a branch in every caller's view.
Take the value instead and let the caller check once.
Checks then migrate up the call chain and collapse: two conditions split across `g` and `h` hide a dead branch that is obvious when they sit together.
The "dissolving enum" is the same move: when `f` picks a variant and `g` matches on it, the condition is evaluated twice, and pulling both branches into one function evaluates it once.

**Push fors down.**
The hot path handles many items, so the batch operation is the base case and the scalar call is the special case.
Batching amortizes setup, allows reordering, and enables struct-of-arrays layouts and vectorization.

**Together.**
An `if` outside a `for` evaluates the condition once and leaves the loop branch-free.
A `for` outside an `if` re-evaluates it per item and blocks vectorization.
TigerBeetle's control plane decides once per batch; its data plane runs the batch.

## Pair assertions

TigerBeetle, [It Takes Two to Contract](https://tigerbeetle.com/blog/2023-12-27-it-takes-two-to-contract).

Design by contract reduces to types plus assertions: a precondition is an assert at the top, a postcondition is a deferred assert.
A contract has two parties, so a real contract needs the assertion at the definition site and at the call site.
The caller asserts the count a function returned is at most the buffer length; the function asserts the same before returning.
A sender asserts a message's invariants from its local view; the receiver re-checks them from its own view, and the different phrasing catches different bugs.
Two paths to the same state (replay from empty, load a snapshot) are compared by checksum.

Rules: when you assert something, find the distant code that relies on it and assert there too.
Pairs across implementations, processes or time are the most valuable.
Paired assertions are defense in depth against a refactor that removes one of them.
Inheritance makes contracts harder to hold, because a subclass must weaken preconditions and strengthen postconditions, which is a reason to avoid inheritance-based polymorphism.

## Simple testing can prevent most critical failures

Yuan et al., [OSDI 2014](https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-yuan.pdf).
A study of 198 user-reported failures in Cassandra, HBase, HDFS, MapReduce and Redis.

- 92% of catastrophic failures resulted from incorrect handling of non-fatal errors explicitly signaled in software.
- 58% could have been caught by simple testing of the error-handling code.
- 35% fell into three trivial patterns a tool or a reviewer catches without system knowledge: the handler is empty or only logs; the handler aborts the whole system on an over-broad catch; the handler contains `TODO` or `FIXME`.
  An HDFS cluster was brought down by an over-catch that called abort.
  Data was lost in HBase by a handler that logged and continued.
- Another 23% were handling logic so wrong that statement coverage of the handler would have caught it.
- 74% of failures were deterministic, and 77% could be reproduced by a unit test.

The authors built Aspirator, a checker for the three trivial patterns, and found 500 new bugs and bad practices in nine systems. ruff's `BLE001`, `E722`, `S110`, `TRY` and `FIX` rules are that checker for Python.

## Let Over Lambda, chapter 1

Hoyte, [Introduction](https://letoverlambda.com/index.cl/guest/chap1.html).

Style is not something to pursue directly.
A novice who avoids pointers in C writes FORTRAN in C, and the disease is ignorance of the language, not poor style.
Once the features are understood, the right style is obvious.
Copying a style is the practical option only while understanding is missing.

## The Mythical Man-Month

Brooks, [Wikipedia](https://en.wikipedia.org/wiki/The_Mythical_Man-Month).
"Plan to throw one away; you will, anyhow."
The first design is a sketch.
Simplicity is reached by revision.

## Fail-fast

[Wikipedia](https://en.wikipedia.org/wiki/Fail-fast).
A fail-fast system reports a failure at its interface as soon as it is detected and stops, rather than continuing in a possibly inconsistent state.
Detecting a violation early is cheaper than diagnosing its consequence later.
A bounded loop that raises on its bound is fail-fast; one that spins is not.

## TOCTOU

[Wikipedia](https://en.wikipedia.org/wiki/Time-of-check_to_time-of-use).
A race where a condition is checked and the result is used after the state could have changed.
TigerStyle's POCPOU generalizes it: a check far from its use in code is a gap in space that the reader cannot verify, as a check far from its use in time is a gap an adversary can exploit.
In Python, an `await` between a check and its use is the time gap.

## Heartbleed

[Wikipedia](https://en.wikipedia.org/wiki/Heartbleed).
A buffer over-read in OpenSSL's heartbeat extension returned up to 64 KiB of process memory because a length field was trusted without a bounds check.
TigerStyle's "buffer bleed" is the related under-fill, where unused padding is not zeroed and leaks.
In Python the lesson reduces to: validate a length against the data it describes before using it to slice.

## Compile-time assertions in TigerBeetle

[journal.zig](https://github.com/coilhq/tigerbeetle/blob/db789acfb93584e5cb9f331f9d6092ef90b53ea6/src/vsr/journal.zig#L45-L47) asserts at compile time that `slot_count` is positive, even, a multiple of the headers per sector, and larger than the pipeline maximum, with a comment explaining the last one. [ewah.zig](https://github.com/coilhq/tigerbeetle/blob/578ac603326e1d3d33532701cb9285d5d2532fe7/src/ewah.zig#L41-L53) asserts that the word type is unsigned, a multiple of a byte, and that a marker is exactly one word.
Each check documents a design invariant and enforces it before the program runs.
In Python, a `Literal`, a `Final`, a `TypedDict` with `total=True`, and `assert_never` in a `match` do the same job through the type checker, and a module-level `if ...: raise` does it at import time.

## Hot loop extraction

[compaction.zig](https://github.com/tigerbeetle/tigerbeetle/blob/0.16.19/src/lsm/compaction.zig#L1932-L1937).
`values_merge` takes three slices and a boolean, no `self`, and asserts the bounds of each slice at entry.
The compiler need not prove it can cache struct fields in registers, and a reader can spot a redundant computation.
In Python the same shape removes attribute lookups from the loop body and makes the function trivially testable.

## Zig SHOWTIME talk, July 2021

[YouTube, from 32:38](https://youtu.be/BH2jvJ74npM?t=1958).
Batching lets the control plane assert heavily once per batch while the data plane stays fast, so assertion safety and performance stop trading against each other.
