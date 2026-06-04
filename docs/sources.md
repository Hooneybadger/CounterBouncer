# 출처

열람일 2026-09-08. 로컬 소스 커밋과 이미지 digest는 `artifacts/setup/provenance.json`에 있다. 이 파일은 git에 없다.

- Linux perf stat JSON: https://man7.org/linux/man-pages/man1/perf-stat.1.html
- Linux 이벤트 그룹/multiplexing: https://github.com/torvalds/linux/blob/master/tools/perf/Documentation/perf-list.txt
- perf 접근 제어: https://www.kernel.org/doc/html/latest/admin-guide/perf-security.html
- PARSEC: https://github.com/csail-csg/parsec
- Ubuntu 설치와 원본 입력 미러: https://github.com/cirosantilli/parsec-benchmark
- CloudSuite: https://github.com/parsa-epfl/cloudsuite
- Data Caching: https://github.com/parsa-epfl/cloudsuite/blob/main/docs/benchmarks/data-caching.md
- 공식 loader v4.0: https://github.com/parsa-epfl/memcached-loadtester/tree/v4.0
- STREAM: https://github.com/jeffhammond/STREAM
- Azure VM Noise Dataset 2024: https://github.com/Azure/AzurePublicDataset/blob/master/AzureVMNoiseDataset2024.md

Azure 인용: Johannes Freischuetz, Konstantinos Kanellis, Brian Kroth, and Shivaram Venkataraman. 2025. TUNA: Tuning Unstable and Noisy Cloud Applications. EuroSys '25. 데이터셋은 CC-BY. upstream LICENSE는 `vendor/azure`에 그대로 둔다. 벤치마크 소스·입력 라이선스는 각 upstream에 있다. vendor 코드, 데이터셋, 이미지는 CounterBouncer 원저작으로 다시 올리지 않는다.
