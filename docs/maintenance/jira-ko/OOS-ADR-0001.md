## OOS-ADR-0001: OOS 파일 비순번(non-numerable) 전환 및 sector-bitmap 열거

- **원제**: OOS pages use a non-numerable file enumerated by a sector-bitmap scan
- **상태**: `accepted`
- **Last updated**: `2026-06-18`
- **개정·대체 관계**: 없음
- **관련 CBRD**: [CBRD-26831](https://jira.cubrid.org/browse/CBRD-26831), [CBRD-26786](https://jira.cubrid.org/browse/CBRD-26786)
- **원문(GitHub SoT)**: [docs/adr/0001-oos-page-enumeration-non-numerable.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0001-oos-page-enumeration-non-numerable.md) (기준 커밋 `139ec89`)

### 배경

기존 `FILE_OOS` 는 `is_numerable=true` 로 생성되어 CUBRID 내 유일한 "항상 영구(permanent)이면서 numerable"인 파일 유형이었다. 페이지 단위 vacuum 회수(deallocation)가 연결되면 mark-delete 항목이 누적되면서 `file_numerable_find_nth` 가 호출당 O(n), bestspace sync 최악 O(max_iterations * n) 경로로 빠지며, `find_nth_last` 속도 캐시도 임시 파일 전용이라 영구 OOS 파일은 사용할 수 없다.

### 결정

1. vacuum 페이지 회수 경로를 연결하기 전에 `FILE_OOS` 를 **비순번(non-numerable)** 영구 파일로 전환한다.
2. `oos_stats_sync_bestspace` 의 `file_numerable_find_nth` 루프를 `file_get_all_data_sectors` 기반 **sector-bitmap walk** (VPID 기준 재개)로 교체한다.
3. 부분/전체 섹터 비트맵은 파일 관리자가 항상 유지하는 기본 메타데이터이므로 페이지별 추가 포맷이나 할당별 WAL 없이 빈 공간 샘플링과 무료에 가까운 페이지 반납(`file_dealloc`)이 가능하다.

### 검토한 대안

- **현행 유지 (numerable + `find_nth`)**: 영구 파일 + 페이지 회수 조합에서 미검증 상태이며, sync가 O(max_iterations * n)으로 저하되고 `FILE_TYPE_CAN_BE_NUMERABLE` 에도 맞지 않아 기각.
- **Heap식 이중 연결 `next_vpid` 페이지 체인**: 모든 OOS 페이지에 체인 레코드를 추가하고 페이지 반납마다 `RVHF_CHAIN` WAL 2회 + 양쪽 이웃 페이지 순서 래치 스플라이스가 필요해 오히려 더 무거워 기각.
- **Sector-bitmap walk (채택)**: 추가 페이지 포맷·WAL 없이 churn 비용이 가장 낮으며, 비트맵 스냅샷의 비동기 동시 반납 레이스만 읽기 경로에서 허용하면 됨.

### 결과 및 영향

- 읽기 전용 bestspace sync 샘플링은 `OLD_PAGE_MAYBE_DEALLOCATED` 로 페이지를 고정하고 `ER_PB_BAD_PAGEID` 를 건너뛰며, 삼킨 레이스를 관측하기 위한 OOS 카운터("sync skipped a deallocated page")를 둔다.
- 실제 삽입/쓰기 경로는 계속 일반 `OLD_PAGE` 를 사용해 해제된 페이지에 쓰는 버그를 즉시 검출한다.
- 할당별 사용자 페이지 테이블 WAL, `RVFL_USER_PAGE_MARK_DELETE` 논리 undo, 헤더 카브아웃이 제거되며, 미사용 `file_numerable_truncate` 와 순번 기준 정렬은 포기한다.
