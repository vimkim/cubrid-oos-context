## OOS-ADR-0011: 빈 OOS 페이지를 반환하지 않고 제자리에서 재사용 (미확정 제안)

- **원제**: Reuse emptied OOS pages in place instead of deallocating them
- **상태**: `proposed` (**미확정 제안 — 확정 규범이 아니며 [CBRD-28281](https://jira.cubrid.org/browse/CBRD-28281) 에서 채택 여부 심의 중**)
- **Last updated**: `2026-11-11`
- **개정·대체 관계**: 채택 시 `OOS-ADR-0009` 결정 3(vacuum fast path 유지) 및 `OOS-ADR-0010` 결정 3(2단계 반환 회수)을 개정함; 현재 `develop` (`PR #7990`)은 `OOS-ADR-0010` 기준임
- **관련 CBRD**: [CBRD-28281](https://jira.cubrid.org/browse/CBRD-28281), [CBRD-27925](https://jira.cubrid.org/browse/CBRD-27925), [CBRD-27872](https://jira.cubrid.org/browse/CBRD-27872)
- **원문(GitHub SoT)**: [docs/adr/0011-reuse-emptied-pages-in-place.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0011-reuse-emptied-pages-in-place.md) (기준 커밋 `139ec89`)

### 배경

`OOS-ADR-0010` 은 빈 페이지를 찾으면 `file_dealloc` sysop(OOS 헤더 페이지 WRITE 래치 점유)으로 파일 관리자에 반환한 뒤 곧바로 두 번째 sysop의 `file_alloc` 으로 다시 받아 초기화한다. 영구 파일 섹터는 `file_destroy` 에서만 디스크로 돌아가므로 이 반환·재할당 왕복과 헤더 래치 경합, 그리고 vacuum fast path의 빈 페이지 목록 전달(`emptied_vpids`)이 불필요한 비용으로 지적되었다(`OOS-ADR-0010` 후속 2단계 계획).

### 제안된 결정 (미확정)

1. **반환 없는 제자리 재사용**: 성장 경로가 `emptied-page set` 이나 lap에서 빈 페이지를 찾으면 `file_dealloc` 과 헤더 페이지 래치 없이 **그 자리에서 바로 쓴다**. OOS 데이터 페이지 반납은 `file_destroy` 에서만 수행한다.
2. **조건부 WRITE 래치 아래 검증 및 즉시 제거**: 조건부 WRITE fix로 `PAGE_OOS`·파일 소유·레코드 없음·공간 충분 여부를 검증하고, 꺼낸 즉시 집합에서 제거한다.
3. **redo-only 재초기화**: 삭제된 슬롯으로 공간이 부족한 빈 페이지는 `RVPGBUF_NEW_PAGE` (redo-only)로 재초기화한 뒤 쓴다(빈 OOS 페이지를 대상으로 하는 undo는 존재하지 않음).
4. **빈 페이지의 bestspace 캐시 제외**: 삭제 후 빈 페이지는 전역 `OOS_BESTSPACE_CACHE` (1,000칸)에 넣지 않고 집합에만 넣어 반쯤 찬 페이지가 캐시에서 밀려 파일이 5% 커지는 현상을 방지한다.
5. **vacuum fast path 제거**: `oos_reclaim_empty_pages`, `vacuum_oos_reclaim_empty_pages`, `oos_delete` 의 `emptied_vpids` 목록 전달을 제거한다.
6. **초기 측정 요약 (`b24fe8741e` 대 `94ed2ea46`)**: DML 로그 레코드 1,000건당 10,166 → 6,241(-39%), `file_alloc`/`file_dealloc` 1,283/240 → 0/0, 대량 UPDATE 중앙값 개선(2,000행 128.8 → 110.8ms, 6,000행 385.8 → 334.0ms), 섹터 수 동일(32 / 94).

### 검토한 대안 및 미결 쟁점

- **현행 `OOS-ADR-0010` 유지 vs `OOS-ADR-0011` 채택**: `CBRD-28281` 에서 다음 쟁점을 심의 중이다 — (1) 2026-11-05 미팅의 fast path 유지 결정 변경 허용 여부, (2) 빈 페이지가 할당 상태로 남아 `SHOW HEAP OOS`·`spacedb` 사용 페이지 수가 커지는 점, (3) fast path 제거 후 UPDATE 뒤 vacuum drain 시간이 0.34s → 2.4s로 길어진 원인 규명, (4) 재초기화 로그 직후 INSERT 전 크래시 및 다중 OOS 파일 동시 churn 검증.

### 예상 결과 및 영향 (채택 시)

- 로그·저장 포맷 변경 없이 DML 중 페이지 반납/할당 sysop과 fast path 배관 코드를 제거할 수 있다.
- 채택 여부가 확정되기 전까지는 `OOS-ADR-0010` 이 공식 규범이며, 이 문서는 `proposed` 상태를 유지한다.
