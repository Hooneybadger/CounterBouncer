# 실험 재현

저장소 루트에서 Python 3.11 이상을 씁니다. `manifest.yaml`이 조건과
반복 횟수를 고정합니다. 원시 결과는 git 밖입니다. 용량 때문입니다.
각 run은 커밋, 매니페스트/정책, 입력·실행 파일 해시에 연결됩니다.

```console
python3 -m venv .venv
.venv/bin/pip install -e '.[analysis,test]'
python3 scripts/preflight.py --output artifacts/preflight/reproduction/system.json
.venv/bin/python scripts/fetch_sources.py
bash scripts/setup_parsec.sh
bash scripts/setup_cloudsuite.sh
bash scripts/build_calibration.sh
```

체크인된 정책은 이미 동결돼 있습니다. 같은 실험을 재현하려면 그 파일을
그대로 둡니다.

```console
.venv/bin/python scripts/run_matrix.py
.venv/bin/python analysis/analyze.py
.venv/bin/python analysis/plots.py
.venv/bin/python analysis/azure.py
.venv/bin/python scripts/audit_results.py
```

`analysis/plots.py`와 `analysis/azure.py`는 `artifacts/`에 원본을 쓰고
GitHub에서 열리는 복사본을 `docs/figures/`에도 둡니다. README는 손으로
유지합니다. `scripts/write_portfolio.py`가 README를 덮어쓰지 않습니다.

## 재개와 실패

run matrix는 매니페스트가 같고 이미 끝난 `run_id`만 이어서 합니다.
중간에 끊긴 run은 보존하고 살펴보기 전에는 재개를 멈춥니다. 실패를
조용히 덮지 않습니다. warmup은 본측정과 별도입니다. 이번 캠페인에서
조사한 중단분은 `artifacts/interrupted/`에 있고 holdout에는 들어가지
않습니다. 측정 matrix와 동시에 빌드·다운로드·분석이나 다른
CounterBouncer 벤치마크를 돌리지 않습니다.

새 머신이면 실험을 따로 만들고 calibration을 새로 모은 뒤, 그
holdout 전에 정책을 새로 freeze합니다. 지금 있는 정책을 다시 맞추지
않습니다. 여기 적힌 topology·PMU 이름은 이 호스트 전용이라 다시
검사해야 합니다.

## CloudSuite 컨테이너

소스 fetcher는 `configs/sources.yaml`에 커밋과 이미지 digest를
고정합니다. CloudSuite 설치는 그 이미지가 있다고 보고
`counterbouncer-dc-server`, `counterbouncer-dc-client`,
`counterbouncer-net`만 만듭니다. 처음 설치가 데이터셋을 스케일·워밍합니다.
측정 중에는 스케일을 반복하지 않습니다. 이미지 digest는
`artifacts/setup`에 있습니다. 호스트 포트는 열지 않습니다.

재현이 끝나면 더 이상 필요 없을 때 그 컨테이너 두 개와
`counterbouncer-net`만 정지·삭제합니다. 예전 이름 `metrictrust-dc-*`가
남아 있으면 같이 지웁니다.
