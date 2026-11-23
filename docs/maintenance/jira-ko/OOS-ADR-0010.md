## OOS-ADR-0010: 청크 삭제 카운터 대신 emptied-page set으로 성장 게이트 회수 트리거

- **원제**: Arm growth-side reclaim with emptied pages, not chunk deletes
- **상태**: `accepted`
- **Last updated**: `2026-11-09`
- **개정·대체 관계**: `OOS-CONTEXT.md` §4 성장 게이트 sweep 메커니즘 개정(`Pending-delete counter` 대체); 향후 `OOS-ADR-0011` 채택 시 결정 3 개정 예정
- **관련 CBRD**: [CBRD-27925](https://jira.cubrid.org/browse/CBRD-27925), [CBRD-27872](https://jira.cubrid.org/browse/CBRD-27872)
- **원문(GitHub SoT)**: [docs/adr/0010-arm-growth-reclaim-with-emptied-pages.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0010-arm-growth-reclaim-with-emptied-pages.md) (기준 커밋 `139ec89`)

### 배경

기존 구현은 페이지가 비었는지와 무관하게 모든 `oos_delete` 마다 성장 게이트를 무장(arm)해, 다음 INSERT 성장이 파일 전체(약 20,000페이지 규모) 섹터 테이블을 정렬하고 할당 페이지를 모두 READ-fix 하며 훑는 심각한 지연을 유발했다(`CBRD-27872`). 또한 INSERT 롤백이 페이지 WRITE 래치를 쥔 동안 sweep이 건너뛰고 카운터를 지워 빈 페이지가 방치되는 경합 결함도 존재했다.

### 결정

1. **파일별 `emptied-page set` 도입**: 각 OOS 파일은 bestspace mutex 아래 크기 제한이 있는 인메모리 빈 페이지 집합(`{emptied pages, unknown, sweep_cursor}`)을 유지한다.
2. **등록 시점**: 페이지를 완전히 비게 만든 경로(`oos_delete_chain`, `OOS-ADR-0008` reclaimer, `oos_rv_redo_delete`, 할당 후 첫 삽입 전 실패 경로 등)만 해당 페이지를 집합에 넣는다. 페이지에 레코드가 남아 있으면 무장하지 않는다.
3. **성장 게이트 검사 및 단일 성장 잠금**: 새 페이지 할당 전 집합 원소를 기존 2단계 회수로 확인하며, 파일당 하나의 성장만 실행해 **집합 검사부터 `file_alloc` 까지** 잠금을 유지한다. 삽입 시 집합에서 제거하고, 래치 경합으로 바쁜 페이지는 집합에 남긴다.
4. **불완전 시 복구(`unknown` 표시)**: 재시작, 집합 삽입 실패, 상한 초과 시 `unknown` 으로 표시하고, 다음 성장이 `oos_reclaim_sweep_step` 1회 완주(lap) 후 집합을 재확인한 뒤 할당한다(lap 중 오버플로가 나면 `unknown` 유지).
5. **기존 `Pending-delete counter` 제거**.
6. **`RVOOS_INSERT` undo에 8B OOS VFID 추가**: 롤백 복구 경로가 페이지를 비웠을 때 어느 파일의 집합에 넣을지 알 수 있도록 undo 데이터에 VFID를 싣는다(리비전은 1 유지).
7. **`CBRD-27872` 측정 기준 통과 (2026-11-09)**: 약 20,000페이지 OOS 파일에서 삭제·vacuum 후 INSERT 중앙값이 51ms(20,000페이지 fix) → 4.6ms(42페이지 fix)로, 동시 8개 성장 INSERT 최악치가 69ms → 5.9ms로 개선되었으며 섹터 수는 동일.

### 검토한 대안

- **현행 게이트에서 바쁜 페이지만 `DEFERRED` 로 별도 재시도**: INSERT 중 동시 쓰기가 있으면 파일 크기 유계가 깨지거나 불필요한 전체 스캔 비용이 그대로 남아 기각.
- **할당당 N개 페이지만 검사(예산 제한)**: "회수 가능 빈 페이지가 있으면 새 섹터 예약 금지" 불변식(`OOS-ADR-0009` 결정 2) 위반으로 기각.
- **Emptied-page set (채택)**: TLA+ 모델과 성장 아레나 검증에서 동시 쓰기·재시작·오버플로 조건에서도 불변식과 파일 크기 상한을 지켰으며, 빈 페이지가 없을 때 추가 페이지를 전혀 읽지 않는다.

### 결과 및 영향

- OOS 페이지를 비우는 모든 코드 경로가 집합 등록 훅을 호출해야 하며(fast path용 `emptied_vpids` 유무와 무관), 누락 시 재시작 전까지 해당 페이지가 고립될 수 있다.
- `RVOOS_INSERT` undo 이미지가 8B 늘어나며(오래된 로그는 fallback으로 처리), 2단계 후속으로 제자리 재사용(`OOS-ADR-0011`, 현재 `proposed`)을 별도 순서로 분리했다.
