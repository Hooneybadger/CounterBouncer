# 진행 기록 — 2026-09-08

명세 §7에 따라 구현 전에 preflight를 만들고 실행했다. 첫 검사 결과는 **BLOCKER A — perf hardware event 접근 불가**. 아래 권한 기록을 본다.

## 확인한 사실

- Intel Core i9-14900K, Linux x86-64. systemd-detect-virt 결과는 none.
- CPU topology와 SMT sibling 목록은 `artifacts/preflight/system.json`에 있다.
- Python 3.12.3, perf 7.0.12, C 컴파일러는 쓸 수 있다.
- Docker 클라이언트와 daemon은 응답했다.
- `kernel.perf_event_paranoid=4`. 기본 이벤트 9개가 모두 권한 메시지와 함께 실패했다.
- perf 실행 파일에 capability가 없다. `sudo -n true`는 비밀번호가 필요해서 실패했다.
- 이 결과는 event unsupported가 아니다. 권한을 푼 뒤 다시 검사해야 한다.
- 당시에는 실제 애플리케이션 벤치마크 설치/실행, calibration, threshold freeze를 아직 하지 않았다.
- 성능 결과나 quality verdict도 만들지 않았다.

## 재개 절차

관리자 터미널에서 측정 권한을 열어야 한다. 프로세스 단위 user/kernel 측정을 잠시 허용하는 예:

```sh
sudo sysctl -w kernel.perf_event_paranoid=1
python3 scripts/preflight.py --output artifacts/preflight/recheck/system.json
```

이 sysctl은 호스트 사용자 전체에 적용되고 재부팅 없이 영구이지는 않다. 되돌리려면 `sudo sysctl -w kernel.perf_event_paranoid=4`. 공유 호스트에서 사용자별로 열려면 관리자가 전용 perf 그룹과 `CAP_PERFMON`을 구성한다. 근거: https://www.kernel.org/doc/html/latest/admin-guide/perf-security.html

Preflight 종료 코드 0은 환경 검사 통과, 2는 차단이다. 첫 실패 기록을 남기려면 재검사 때 `--output`을 다른 경로로 둔다.

## 다음 구현 순서

1. perf JSON parser와 누락/unsupported/not-counted/하이브리드 PMU 테스트.
2. 이벤트 group, 원시 출력 보존 runner, environment collector.
3. calibration과 후보 threshold. real workload를 보기 전에 freeze.
4. PARSEC native 4종, CloudSuite 1종 adapter와 outcome parser.
5. CLEAN과 contamination matrix, 반복 안정성, 근거 코드.
6. Azure 외부 분석, 실측 Figure 5장과 보고서.

i9-14900K topology를 보고 pinning 구간과 sibling을 고른다. 서로 다른 PMU의 cycles/instructions를 무조건 더해 IPC를 만들지 않는다.

## 검증

- `python3 scripts/preflight.py` 실제 실행: 종료 코드 2, BLOCKER A 저장.
- `python3 -m py_compile scripts/preflight.py` 통과.
- 각 probe의 command/returncode/stdout/stderr와 원시 perf 파일을 보존.

## 권한 해결과 parser

사용자 승인 뒤 관리자 권한으로 `perf_event_paranoid`를 잠시 1로 바꿨다. 비밀번호는 프로젝트 파일에 넣지 않았고 sudo 인증 캐시는 비웠다. 재검사: `artifacts/preflight/authorized/system.json`, 종료 코드 0 (READY). 첫 실패 자료는 그대로 있다. READY는 최소 환경 검사 통과이지, 최종 실험 품질 보증이 아니다.

하이브리드 PMU에서는 돌지 않은 PMU의 not-counted와 다른 PMU의 유효 카운터가 같이 나올 수 있다. preflight는 이를 `partially_available`로 남긴다.

`counterbouncer/perf_parser.py`를 만들었다. PMU 이름과 원시 field, variance를 남기고 unsupported/not-counted는 null이다. JSON이 깨지면 예외로 보고한다. 합성 unit test 입력은 `tests` 안에만 있고 벤치마크 증거로 쓰지 않는다.

검증: `python3 -m unittest discover -s tests -v` — 5개 통과. 실제 authorized preflight raw 파일 9개도 parser로 읽었다. 다음 작업은 group/affinity를 명시한 runner, quality hard rules, calibration이었다.

## 끝까지 수행 요청 이후 개발 중 본 것

- PARSEC native archive 다운로드와 패키지 4개 빌드 성공.
- CloudSuite 공식 server/client 이미지, Twitter 28x 적재 성공.
- 첫 calibration 시도가 CloudSuite sanity/외부 분석과 겹친 것을 보고 중단했다. 그 데이터는 `artifacts/calibration-development-overlap`에 전부 두고 threshold freeze에서 뺐다. setup/sanity가 끝난 뒤 calibration을 다시 모았다.
- CloudSuite 출력은 비TTY에서 버퍼링되므로 `docker exec -t`로 공식 loader 통계를 남긴다.

## 2026-09-08 세션 재개

native-holdout-v1 실행기가 세션 종료로 끊겼다. `parsec-canneal-unpinned-r02`는 `status=running`이었고 남은 canneal/perf 프로세스는 없었다. stdout에 종료 문구는 있었으나 returncode·wall time·parsed events·quality가 없어 측정으로 넣지 않았다. 원본은 `artifacts/interrupted/parsec-canneal-unpinned-r02`에 두고 같은 `run_id`로 다시 시도했다. 정책 파일은 바꾸지 않았다.

CloudSuite Data Caching holdout은 그때 아직 시작하지 않았다. 12초 sanity는 통계가 없었고 60초 sanity는 interval을 냈다. 로더 시작 시간을 반영해 `duration_s`를 15에서 60으로 holdout 전에 고쳤다. 품질 threshold는 그대로다.

PARSEC 4종 native holdout 200회는 끝났다. 이어서 메모리에 남아 있던 `duration_s=15` 프로세스가 CloudSuite warmup과 일부 run을 시작했다. 그 15초 산출물은 `artifacts/interrupted/cloudsuite-15s-before-amendment`에 두고 같은 experiment ID에서 60초 timeout으로 CloudSuite holdout을 다시 시작했다.

## 완료 (2026-09-08)

native-holdout-v1: PARSEC 4종 × 5 조건 × 10회 = 200, CloudSuite Data Caching 5 조건 × 5회 = 25. 실행 실패 0. `scripts/audit_results.py` → PASS. Figure 5장은 측정 artifact에서 그렸고 GitHub에 보이는 복사본은 `docs/figures/`다. README는 측정 숫자를 설명하는 문서이지, 스크립트가 덮어쓰는 포트폴리오 템플릿이 아니다. 정책은 holdout 이후 다시 맞추지 않았다.
