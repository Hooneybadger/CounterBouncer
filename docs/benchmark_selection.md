# Benchmark selection

PARSEC 3.0 in `native-holdout-v1`: blackscholes (compute / finance),
canneal (routing-style irregular memory), dedup (data pipeline),
streamcluster (streaming clustering). `native-holdout-v2` keeps
blackscholes and canneal, adds freqmine (OpenMP frequent-pattern)
and swaptions (derivatives). Four threads. `native.runconf` arguments
are unchanged.

Native inputs are the original archives mirrored by
cirosantilli/parsec-benchmark. The csail-csg fork is centered on
RISC-V cross builds; x86-64 uses the Ubuntu-runnable tree. Archive
hashes, source commits, compiler output, and build failures land in
local `artifacts/setup`.

CloudSuite Data Caching: official image, Twitter dataset x28, server
10 GB, 4 server threads, 8 client threads, 200 connections, get
ratio 0.8. After the loader is up, offered load is fixed at 100,000
req/s for 60 s. This is a measurement-quality experiment, not a
search for peak sustainable throughput. Network is a dedicated
Docker bridge on one host. Other containers already running were
left up and recorded as a shared-host limit.

Calibration uses local branch-predict / working-set kernels and a
local STREAM-like triad for memory interference. Official STREAM C
ran only as a pipeline check after policy freeze. It is not used to
talk about application performance.

Official streamcluster native takes `none` as the input file and
builds points internally. That package has no native input archive.
swaptions native is CLI arguments only, no input archive. These are
the official application-benchmark settings, not ad-hoc workloads.
Provenance stores the `native.runconf` hash for those cases.
