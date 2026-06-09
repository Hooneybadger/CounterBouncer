# Sources

Local source commits and image digests are in
`artifacts/setup/provenance.json`. That file is not in git; it lives
under local `artifacts/`.

- Linux perf stat JSON: https://man7.org/linux/man-pages/man1/perf-stat.1.html
- Linux event groups / multiplexing: https://github.com/torvalds/linux/blob/master/tools/perf/Documentation/perf-list.txt
- perf access control: https://www.kernel.org/doc/html/latest/admin-guide/perf-security.html
- PARSEC: https://github.com/csail-csg/parsec
- Ubuntu install and original input mirror: https://github.com/cirosantilli/parsec-benchmark
- CloudSuite: https://github.com/parsa-epfl/cloudsuite
- Data Caching: https://github.com/parsa-epfl/cloudsuite/blob/main/docs/benchmarks/data-caching.md
- Official loader v4.0: https://github.com/parsa-epfl/memcached-loadtester/tree/v4.0
- STREAM: https://github.com/jeffhammond/STREAM
- Azure VM Noise Dataset 2024: https://github.com/Azure/AzurePublicDataset/blob/master/AzureVMNoiseDataset2024.md

Azure citation: Johannes Freischuetz, Konstantinos Kanellis, Brian
Kroth, and Shivaram Venkataraman. 2025. TUNA: Tuning Unstable and
Noisy Cloud Applications. EuroSys '25. Dataset is CC-BY. Upstream
LICENSE stays under `vendor/azure`. Benchmark source and input
licenses are each upstream's. Vendor code, datasets, and images are
not re-published as original work of this repository.
