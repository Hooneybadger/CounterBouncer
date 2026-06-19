# 서버 정확 측정 방법 (throttle + daemon)

조직위 확정(2026-06-19): 서버 = firejail+cpulimit **400% throttling**(코어 보이나 총량 4코어, 초과시
느려질뿐 안죽음), multiprocessing 허용, worker=4 권장. 실행은 **한 번에 한 인스턴스**.

## 반드시 1개씩 측정
`daemon_spot.py`/배치에 인스턴스 여러 개를 *동시* 주면 N배 oversubscription = 서버 아닌 조건(아티팩트).
서버는 1개씩이므로 **`seq_run.py`(1개씩 순차) + `systemd-run CPUQuota=400%`** 로만 측정한다.

```bash
# 서버 완전 모사 (1개씩 + 400% throttle)
systemd-run --user --scope -p CPUQuota=400% --quiet \
  conda run -n ogc2026 python learning/seq_run.py 60 prob_38 prob_26 prob_28
# relax ON/OFF 진단: relax_diag_seq.py
# 실험 노브: OGC_NW(워커수)·OGC_CP_WORKERS(CP스레드)·OGC_NO_RELAX
```

## 측정된 결론 (v1.2.0)
- throttle ≈ 비-throttle (1개씩이면): relax-OFF prob_38=69,994,299 = v1.1.0 비-throttle와 정확 일치.
  → "throttle 5~23% 저하"는 동시실행 아티팩트였음(기각).
- **nw=4가 최적**: nw=5는 CP단계 8스레드로 CP-SAT 굶겨 prob_38 +11.6%(relax 죽음). 조직위 worker=4 권장 일치.
- relax는 서버 정확조건서 작동(5/7 obj1 개선). v1.1.1(os.fork)이 서버서 처음 활성.
