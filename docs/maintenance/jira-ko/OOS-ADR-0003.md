## OOS-ADR-0003: 원시 바이트 소비자 전용 opt-in OOS 레코드 Expand 계약

- **원제**: OOS record expansion is opt-in for raw-byte consumers
- **상태**: `accepted`
- **Last updated**: `2026-07-13`
- **개정·대체 관계**: 없음
- **관련 CBRD**: [CBRD-26847](https://jira.cubrid.org/browse/CBRD-26847), [CBRD-26948](https://jira.cubrid.org/browse/CBRD-26948)
- **원문(GitHub SoT)**: [docs/adr/0003-oos-expansion-is-opt-in.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0003-oos-expansion-is-opt-in.md) (기준 커밋 `139ec89`)

### 배경

가시 버전 힙 조회 함수(`heap_get_visible_version`, `heap_scan_get_visible_version`, `heap_get_last_version`)가 매번 모든 OOS 스터브를 즉시 확장(Expand)하면, 큰 값을 핫 패스 밖으로 분리해 I/O를 줄이려는 OOS의 본래 목적이 무력화된다.

### 결정

1. OOS 레코드 확장(**Expand**)은 **opt-in** 계약으로 유지한다. `heap_get_visible_version_expand_oos` 만 `HEAP_GET_CONTEXT.expand_oos = true` 를 설정해 `heap_record_replace_oos_oids` 가 전체 `RECDES` 를 재구성하도록 한다.
2. 소비자 성격에 따라 조회 계약을 구분한다:
   - **Expand (레코드 단위, 즉시, 전체 레코드)**: 클라이언트 `LC_COPYAREA` 전송, 다른 힙으로의 재삽입, 바이트 단위 비교, `OR_BUF` 직접 파싱 등 **원시 `RECDES` 바이트**를 소비하는 경로에만 사용한다.
   - **Resolve (속성 단위, 지연)**: 속성 계층(`heap_attrinfo_read_dbvalues` → `heap_attrvalue_read_oos_inline` → `oos_read`)을 통해 접근된 속성만 읽거나, 고정 컬럼·헤더·CHN·존재 여부만 필요한 경로는 기본 cheap fetch 를 사용한다.

### 검토한 대안

- **항상 Expand**: 저장 프로시저(SP) fetch, UPDATE 구버전 읽기, 조인 스캔 등 핫 패스에서 OOS I/O 절감 효과를 없애므로 기각.
- **Opt-in Expand (채택)**: 기본 조회를 가볍게 유지하고 원시 바이트 소비자만 명시적으로 Expand 를 선택.

### 결과 및 영향

- `CBRD-26847` 전수 조사에서 `xlocator_lock_and_fetch_all`, `redistribute_partition_data`, `catcls_delete_instance`, `catcls_update_instance`, `catcls_update_class_stats` 등 5개 원시 바이트 소비자가 Expand 필수 대상으로 식별되었다.
- 반대로 원시 바이트 경로가 Expand 를 누락하면 OOS 비인식 소비자에게 스터브가 유출되는 위험이 있다(`xlocator_fetch_all` → `unloaddb`/`compactdb` 사례, `CBRD-26948`).
- 새로운 힙 조회 호출자는 선택한 계약을 정당화해야 하며, `_expand_oos` 접미사가 원시 바이트 노출 경계를 나타낸다.
