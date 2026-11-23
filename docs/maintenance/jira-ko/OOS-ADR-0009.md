## OOS-ADR-0009: 빈 OOS 페이지는 유휴 시가 아닌 파일 성장 전에만 회수·재사용

- **원제**: Reclaim empty OOS pages before growth, not while the file is idle
- **상태**: `accepted`
- **Last updated**: `2026-11-06`
- **개정·대체 관계**: `OOS-CONTEXT.md` §4 빈 페이지 회수 불변식(`CBRD-26786`, 2026-08-28) 개정; 향후 `OOS-ADR-0011` 채택 시 결정 3 개정 예정
- **관련 CBRD**: [CBRD-27925](https://jira.cubrid.org/browse/CBRD-27925), [CBRD-26786](https://jira.cubrid.org/browse/CBRD-26786)
- **원문(GitHub SoT)**: [docs/adr/0009-reclaim-empty-pages-before-growth-not-while-idle.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0009-reclaim-empty-pages-before-growth-not-while-idle.md) (기준 커밋 `139ec89`)

### 배경

기존 `CBRD-26786` 불변식은 "빈 페이지를 결국 파일 관리자에게 반환한다"고 적어, `CBRD-26659` 회수 테스트 5건이 추가 쓰기 없이 20초를 기다리며 페이지 수가 즉시 줄어들기를 기대해 실패했다. 그러나 영구 파일은 `file_destroy` 에서만 디스크에 섹터를 돌려주며(`file_dealloc` 은 같은 파일의 partial 섹터 테이블로만 되돌림), 유휴 중 반납해도 디스크 공간이 줄거나 다른 테이블이 그 페이지를 쓸 수 없다.

### 결정

1. **유휴 시 반환 의무 제거**: 빈 OOS 데이터 페이지는 파일이 할당을 받지 않는 유휴 상태에서 반환할 필요가 없으며, **새 섹터를 예약하기 전에** 회수 또는 재사용되어야 한다.
2. **성장 측 불변식 유지**: 안전한 회수 가능 빈 페이지가 지금 존재할 때는 새 섹터를 예약하지 않는다. 인메모리 힌트 유실·재시작·롤백·래치 경합이 이 규칙을 깨뜨려서는 안 된다.
3. **2중 구조 유지**: vacuum fast path(최적화)와 growth-gate sweep(보장)을 유지한다.
4. **테스트 판정 기준 개정**: 유휴 대기 대신 반복(최소 5회) churn 워크로드를 실행하고, 매 cycle 최대 페이지 수가 첫 cycle 최대치 + `max(2 pages, 10%)` 허용 오차 이내이며 재적재 후 예약 섹터 수가 첫 피크를 넘지 않음을 검증한다.

### 검토한 대안

- **유휴 파일 백그라운드 재방문 메커니즘 추가**: 디스크 회수나 타 테이블 공간 공유 이득이 전혀 없는 상태에서 백그라운드 태스크와 동시성 비용만 추가되므로 기각.
- **성장 전 회수·재사용 불변식으로 정정 (채택)**: 실제 공간 소비자인 "같은 OOS 파일의 다음 할당" 시점에 정확히 회수·재사용을 보장.

### 결과 및 영향

- `SHOW HEAP OOS` 와 `spacedb` 에서 유휴 상태의 빈 페이지가 할당된 사용자 페이지로 보일 수 있으며 이는 정상 동작이다.
- `CBRD-27925` 는 유휴 재방문 경로 없이 성장 측 힌트 유실·래치 경합 및 fast path 후보 공급 보장에 집중할 수 있게 되었다.
- `CBRD-26659` 회수 테스트 5건은 유휴 페이지 감소 oracle에서 "성장 전 재사용" oracle로 전환된다.
