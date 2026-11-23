## OOS-ADR-0002: BLOB/CLOB locator 컬럼의 OOS demotion 자격 유지

- **원제**: BLOB/CLOB locator columns remain OOS-demotable (type-agnostic eligibility)
- **상태**: `accepted`
- **Last updated**: `2026-07-13`
- **개정·대체 관계**: 없음
- **관련 CBRD**: [CBRD-26814](https://jira.cubrid.org/browse/CBRD-26814)
- **원문(GitHub SoT)**: [docs/adr/0002-oos-lob-locator-demotion.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0002-oos-lob-locator-demotion.md) (기준 커밋 `139ec89`)

### 배경

BLOB/CLOB 컬럼의 행 내부 값은 외부 LOB 저장소(`es.c`)를 가리키는 `DB_ELO` locator(실무상 약 88B 경로 문자열)다. `bug_xdbms3693` (BLOB 50 + CLOB 50 컬럼) 크래시 분석 과정에서 이미 외부 참조인 LOB locator를 OOS로 한 번 더 옮기는 것을 제외하자는 초기안이 있었으나, 크래시 원인이 스터브 라이터의 경계 검사 버그(`buf->ptr` 대신 실제 `*ptr_varvals` 를 검사해야 함)로 규명되고 OOS 경로의 LOB 복사 의미론이 동등함을 확인하면서 2026-07-02 같은 날 결정을 뒤집어 자격을 유지하기로 확정했다.

### 결정

1. BLOB/CLOB 컬럼도 일반 가변 길이 컬럼과 동일한 규칙(`is_variable && column_size > OR_OOS_INLINE_SIZE`)에 따라 **OOS demotion 대상에 포함**한다.
2. OOS demotion은 **타입 비의존적(type-agnostic)** 메커니즘으로 유지하며, locator 바이트 역시 컬럼의 직렬화 값으로 취급한다.

### 검토한 대안

- **LOB 타입을 OOS 대상에서 유지 (채택)**: 타입별 예외 분기가 없고, `heap_attrinfo_insert_to_oos` → `heap_attrinfo_dbvalue_to_recdes` 가 인라인 경로와 동일한 `db_elo_copy_with_prefix` 분기를 타므로 `INSERT ... SELECT` LOB 복사 의미론이 동일하다. 또한 LOB 컬럼 100개(약 8.8KB locator) 같은 스키마가 4KB 목표를 영구 초과해 막히는 문제를 피할 수 있다.
- **`DB_TYPE_BLOB` / `DB_TYPE_CLOB` 제외**: 바이트 수준 메커니즘에 타입 예외를 추가하며 locator 다수 행의 크기를 줄이지 못해 기각.
- **LOB 본문(payload) 자체를 OOS로 외부화**: `es.c` LOB 서브시스템은 별도 수명 주기를 갖는 다른 기능 영역이므로 범위 외로 제외.

### 결과 및 영향

- OOS로 내려간 locator를 읽을 때는 3단계 간접 참조(`row -> OOS stub -> OOS record -> locator -> LOB file`)가 발생하지만, largest-first 정책상 ~88B locator는 더 큰 일반 컬럼이 모두 빠진 뒤에도 행이 목표를 넘을 때만 마지막으로 내려간다.
- OOS 청크를 vacuum/delete 해도 OOS 내 locator 바이트만 지우며 외부 LOB 파일은 삭제하지 않는다(LOB 파일 수명은 LOB 계층 소유).
- `bug_xdbms3693` 은 인라인 잔여 LOB의 길이 변동과 스터브 `S_DOESNT_FIT` 재시도를 검증하는 대표 회귀 테스트로 남는다.
