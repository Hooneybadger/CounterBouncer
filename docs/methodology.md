# Method

On Linux bare metal, `perf stat` JSON is the record. PARSEC wraps
the official native binary. Unpack and build sit outside the
measured window. Counter interval and runtime both include
application init and file I/O. The window is not clipped to PARSEC
ROI hooks.

CloudSuite attaches to the memcached server's host PID. Docker CLI
and client counters are unused. The client runs on a different CPU
set. The server counter window includes the client command, start-up
included. Loader intervals drop the first two before stats. The
client command is bounded with `timeout` at `duration_s=60`.

## Pin and events

P-core affinity is `2,4,6,8`. SMT contention is `3,5,7,9`. Memory
contention is `24,25,26,27`. PCORE stays inside
`/sys/devices/cpu_core/cpus` (`0-15` on this host). HYBRID is every
present CPU; `cpu_core` then has only partial coverage, on purpose.
IPC is not summed across PMU units.

Migrations inside the pin do not, by themselves, drop integrity.
Observed CPUs of the process tree catch affinity escape, P/E
movement, and NUMA movement.

Counter groups: cycles/instructions, branches/branch-misses,
cache-references/cache-misses. Derived metrics are used only when
event-runtime and pcnt-running match on that pair. missing /
unsupported / not-counted stay null. Requesting independent alias
pairs together produces real multiplexing. Generic cache ratios do
not mean the same thing on every CPU.

REFERENCE requests `{cpu_core/cycles, cpu_core/instructions}` plus
software events. High-coverage minimal group, not an absolute
truth.

## Repeats and labels

Each condition uses the same binary and settings. After one warmup
per workload, condition order is shuffled inside a PARSEC x10 or
CloudSuite x5 block. Every attempt is kept. Condition labels come
from the manifest. The only plot RNG is horizontal jitter.

CLEAN means CounterBouncer added no extra interference. It is not a
dedicated machine. `native-holdout-v2` PARSEC stops the project's
CloudSuite containers first. Other lab containers stay up.

## Policy freeze

Policy candidates are heuristics, not an industry standard.
Calibration collects 10 runs per case before freeze. Runtime CV
degrade is `max(0.05, 3x max CLEAN calibration CV)`; reject is
`max(0.20, 2x degrade)`. Running thresholds stay at the 50/90%
candidates. CloudSuite group stability is interval-p99 CV. Latency
cutoffs were written into the policy file before freeze.

`native-holdout-v1` policy stays in `configs/experiment.yaml`. New
campaigns use only `configs/experiment_v2.yaml`. Holdout numbers do
not retune policy.

Hard verdicts are per run. `HIGH_RUN_VARIANCE` is a group note.
