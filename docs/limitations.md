# Limitations

One shared bare-metal i9-14900K. CLEAN is not a dedicated box.
Project memcached was up during `native-holdout-v1` PARSEC.
`native-holdout-v2` PARSEC stopped that container only.

On HYBRID, `cpu_core` does not count E-core time. Migrations inside
the pin do not, by themselves, drop integrity. freqmine CLEAN x10
ran on CPU `0`.

All 30 CloudSuite runs in `native-holdout-v2` are INVALID: server
threads left the pin. `native-cloudsuite-v2.1` leaves those 30 in
place and adds CLEAN x5 / MEMORY x5 after pinning threads.

p99 is the median of interval p99. The loadtester `timeDiff` quirk
is left as recorded. Runtime CV degrade 0.5086 comes from CLEAN
`cache-large` CV 0.1695; that bar did not attach
`HIGH_RUN_VARIANCE`. v2 holdout has `git_dirty` true. There is no
snapshot of that dirty tree. Local `artifacts/experiment-code.patch`
reconstructs the recorded HEAD against a later committed tree.

Frequency and turbo were left alone. Generic cache is not a stand-in
for LLC or bandwidth. REFERENCE and Azure are not PMU ground truth.
`pcnt-running` cutoffs are heuristics. Time phase and metric class
are not in the gate yet.
