# Reproduce

From the repository root, Python 3.11+. `manifest.yaml` pins
conditions and repeat counts. Raw results stay out of git because
of size. Aggregates and `perf.jsonl` live under local `artifacts/`.
Each run ties to a commit, manifest/policy, and input/binary hashes.

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[analysis,test]'
python3 scripts/preflight.py --output artifacts/preflight/reproduction/system.json
.venv/bin/python scripts/fetch_sources.py
bash scripts/setup_parsec.sh
bash scripts/setup_cloudsuite.sh
bash scripts/build_calibration.sh
```

Checked-in policy is already frozen. Leave those files alone to
reproduce the same experiment.

```console
.venv/bin/python scripts/run_matrix.py
.venv/bin/python analysis/analyze.py
.venv/bin/python analysis/plots.py
.venv/bin/python analysis/azure.py
.venv/bin/python scripts/audit_results.py
```

`native-holdout-v2` is `bash scripts/run_v2_campaign.sh`. Policy is
`configs/experiment_v2.yaml`. The CloudSuite follow-up is
`experiments/manifest_v2_1_cloudsuite.yaml`. Frozen policy stays
frozen.

## Resume and failures

The run matrix continues only `run_id`s that already finished under
the same manifest. A run cut mid-flight is kept; resume stops until
it has been inspected. Failures are kept. Warmup is separate from
the measured set. Interrupted attempts from this campaign sit in
`artifacts/interrupted/` and are not in holdout. During measurement,
do not also build, download, analyze, or run another CounterBouncer
benchmark.

A new machine is a new experiment: collect calibration, freeze
policy, then holdout. Do not reuse the files here as-is. Topology
and PMU names in these docs are this host's and must be rechecked.

## CloudSuite containers

The source fetcher pins commits and image digests in
`configs/sources.yaml`. CloudSuite setup assumes those images exist
and only creates `counterbouncer-dc-server`,
`counterbouncer-dc-client`, and `counterbouncer-net`. First install
scales and warms the dataset. Measurement does not scale again.
Image digests are in `artifacts/setup`. No host ports are published.

When reproduction is done, stop and delete those two containers and
`counterbouncer-net` if you no longer need them. Also drop leftover
`metrictrust-dc-*` names.
