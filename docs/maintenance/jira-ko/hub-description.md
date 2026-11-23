# [OOS] OOS 규범 명세(Spec) 및 아키텍처 결정 기록(OOS-ADR-0001~0011)

**한 줄 요약**: GitHub [vimkim/cubrid-oos-context](https://github.com/vimkim/cubrid-oos-context) 저장소를 단일 원본(Source of Truth)으로 유지하면서, 사내 동료들이 JIRA에서 OOS 규범 명세와 `OOS-ADR-0001`~`0011` 용어 및 설계 결정을 직접 조회·이해할 수 있도록 공식 동기화 허브 이슈를 운영한다.

## Issue Triage

**이슈 수행 목적**: OOS의 규범 명세(`OOS-CONTEXT.md`)와 아키텍처 결정 기록(`OOS-ADR-0001`~`0011`)을 공식 CBRD JIRA 이슈로 동기화하여, 팀·QA·리뷰어가 JIRA 안에서 표준 식별자와 설계 결정을 즉시 찾아 이해할 수 있게 한다.

**이슈 수행 이유**: OOS 구현이 [PR #7990](https://github.com/CUBRID/cubrid/pull/7990) (`68a9c7766f`, 2026-11-19)으로 `develop` 에 병합되었고, 기존 15건의 CBRD 이슈와 외부 코드 리뷰([CBRD-26357](https://jira.cubrid.org/browse/CBRD-26357) 2026-11-19 댓글)가 `cubrid-oos-context` 명세를 기준으로 삼고 있다. 그러나 사내 공식 JIRA에는 해당 Spec과 `OOS-ADR` 목록·내용을 한눈에 볼 수 있는 공식 기준 이슈가 없다.

**영향**: 동료 개발자와 리뷰어가 이슈·PR에서 `OOS-ADR-0008`, `OOS-ADR-0011` 같은 결정 식별자를 접할 때 JIRA 내부 검색만으로 배경과 확정 여부를 확인하기 어렵고, `accepted` 결정과 `proposed` 제안(`OOS-ADR-0011`)을 혼동할 위험이 있다.

**이슈 수행 방안**: 확정된 운영 원칙에 따라 [vimkim/cubrid-oos-context](https://github.com/vimkim/cubrid-oos-context) (`main`)를 단일 원본(SoT)으로 유지하고, 본 이슈를 [CBRD-26357](https://jira.cubrid.org/browse/CBRD-26357) 의 `Sub-task` ([CBRD-26978](https://jira.cubrid.org/browse/CBRD-26978) 연계) 공식 단방향 동기화 허브로 운영한다. 본문에는 동기화 메타데이터·규범 명세 요약·`OOS-ADR` 마스터 인덱스 표(`Last updated` 포함)를 두고, 각 ADR의 상세 결정 요약은 `OOS-ADR-NNNN` 고정 댓글로 1:1 관리한다.

---

## AI-Generated Context

## Source of Truth and Sync Policy

- **단일 원본(Source of Truth)**: [https://github.com/vimkim/cubrid-oos-context](https://github.com/vimkim/cubrid-oos-context) (`main`)
- **동기화 기준 커밋**: `139ec89` (문서 최종 갱신일 `2026-11-19`)
- **단방향 동기화 원칙**: 모든 Spec/ADR 수정은 GitHub `cubrid-oos-context` 에 먼저 반영하고, ADR이 추가되거나 수정될 때마다 본 JIRA 이슈의 마스터 인덱스 표와 해당 `OOS-ADR-NNNN` 댓글을 함께 갱신한다. 본 JIRA 본문이나 댓글을 원본보다 먼저 단독 수정하지 않는다.
- **표준 식별자 규칙**: 사내 JIRA·PR·코드 리뷰에서는 각 결정을 `OOS-ADR-0001`~`OOS-ADR-0011` 형식으로 표기한다.
- **구현과 규범의 구분**: 본 이슈에 정리된 확정 규범(`OOS-CONTEXT.md`, `accepted` ADR)은 요구 동작을 정의하며, 특정 엔진 커밋의 구현 여부나 버그 상태는 개별 CBRD 티켓과 소스를 기준으로 판단한다.

## Normative Specification Summary (OOS-CONTEXT.md)

원문 전체: [OOS-CONTEXT.md](https://github.com/vimkim/cubrid-oos-context/blob/main/OOS-CONTEXT.md) (`2026-11-19`), 이력 용어: [CONTEXT.md](https://github.com/vimkim/cubrid-oos-context/blob/main/CONTEXT.md)

### §1. 트리거·배치·거부 규칙

- **Largest-First 점진적 demotion (`CBRD-26776`, `CBRD-27057`)**: `heap_attrinfo_determine_disk_layout` 에서 레코드 크기(`header_size + payload_size + mvcc_extra`)가 목표치를 넘을 때만 가변 길이 컬럼(`column_size > OR_OOS_INLINE_SIZE`, 즉 24B 초과)을 큰 값부터 하나씩 OOS로 옮긴다. 목표치 이하가 되거나 후보가 소진되면 중단하며, `STORAGE PREFER_INLINE` 컬럼은 일반 후보 뒤 마지막 순위로 밀린다.
- **PG식 4-record 물리 목표**: 기본 목표는 `heap_oos_inline_target_size()` 가 산출하며, 힙 슬롯 4개를 제외한 비헤더 페이지 용량을 4로 나눈 뒤 `HEAP_MAX_ALIGN` (4B)으로 내림 정렬한다. 16KiB I/O 페이지(`DB_PAGESIZE` 16,344B, 비헤더 용량 16,268B) 기준 자동 목표는 **4,060B** 이며 `unfill_space` 와 무관하다.
- **정적 서버 파라미터 `oos_trigger_threshold` (`CBRD-28062`)**: 기본값 `0` 은 자동 목표를 뜻하며 OOS를 비활성화하지 않는다. 0이 아닌 값은 자동 목표 이상 `heap_Maxslotted_reclength` 이하만 허용한다(4KiB: 988~3,948B, 8KiB: 2,012~8,044B, 16KiB: 4,060~16,236B). 시스템 클래스(`_db_serial` 등)는 항상 자동 목표를 사용한다. 서버 기동·`createdb`·`patchdb` 에서 검사하며 `restoredb` 중에는 검사하지 않는다.
- **컬럼 `STORAGE` 정책 (`CBRD-26912`, `CBRD-26067`, `CBRD-27259`)**: 일반 컬럼에 한해 `DEFAULT`/`PREFER_OUTLINE`, `PREFER_INLINE`, `FORCE_INLINE`, `FORCE_OUTLINE` 을 지원한다(고정 길이 타입은 `DEFAULT`/`FORCE_INLINE` 만 허용). `FORCE_INLINE` 으로 `ALTER` 할 때는 기존 모든 행(파티션·하위 클래스 포함)을 새 정책으로 레이아웃 검사해 초과 시 `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` 로 거부한다.
- **`bigone` 거부 (`CBRD-26937`, `CBRD-27259`)**: 시스템 클래스와 루트 클래스를 제외한 행은 demotion 후에도 `REC_BIGONE` 이 필요하면 OOS 체인 삽입 전에 `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` 로 거부한다. 대량 고정 길이 `BIT(n)` 이나 24B 이하 가변 값이 많아 초과한 경우도 거부 대상이다.

### §2. 저장 구조·신원 검사·공간 탐색

- **레코드 및 스터브 레이아웃**: VOT 엔트리의 `IS_OOS` 비트(`OR_VAR_BIT_OOS = 0x1`)가 설정되면 해당 위치에 **24B OOS inline stub**(`head OOS OID` 8B + `full length` 8B + `packed head identity stamp` 8B)이 놓인다. 힙 레코드 MVCC 플래그 `HAS_OOS` (`OR_MVCC_FLAG_HAS_OOS = 0x08`)는 메타데이터이며 MVCC 헤더 크기를 바꾸지 않는다.
- **다중 청크 체인과 32B 헤더**: 한 OOS 페이지를 넘는 값은 tail(`chunk_2`)부터 head(`chunk_0`) 순으로 역순 삽입하고, 읽기는 head부터 순방향으로 재조립한다. 각 청크는 **32B 헤더**(`total_data_length` 4B + `chunk_index` 4B + `next-chunk OID` 8B + `next-chunk stamp` 8B + `identity_stamp` 8B)를 갖는다.
- **신원 스탬프 검증 (`CBRD-26950`)**: 각 청크는 쓰기 래치 아래 캡처한 페이지 LSA를 신원 스탬프로 저장한다. 읽기와 회수기는 스탬프를 비교해 해제·재타입화·슬롯 재사용에 따른 stale 참조를 가려낸다. 로깅이 꺼진 대량 적재(`log_is_no_logging`)에서는 스탬프 유일성이 보장되지 않는 예외를 명시한다.
- **3-Tier Bestspace 및 비순번(non-numerable) 열거 (`CBRD-26658`, `OOS-ADR-0001`)**: `FILE_OOS` 는 힙당 최대 1개 지연 생성되는 비순번 영구 파일이다. 헤더 페이지 0의 `OOS_HDR_STATS` (`best[10]`)와 전역 `OOS_BESTSPACE_CACHE` 로 후보 페이지를 찾고, 미스 시 `file_get_all_data_sectors` 기반 sector-bitmap walk(`OLD_PAGE_MAYBE_DEALLOCATED` 사용)로 빈 공간을 재탐색한다.

### §3. CRUD 및 소유권 계약

- **Resolve vs Expand (`CBRD-26847`, `OOS-ADR-0003`)**: 속성 계층 소비자는 필요한 컬럼만 지연 복원하는 **Resolve** (`heap_attrinfo_read_dbvalues` → `heap_attrvalue_read_oos_inline` → `oos_read`)를 사용한다. 클라이언트 `LC_COPYAREA` 전송·힙 재삽입·바이트 비교·`OR_BUF` 파싱 등 원시 `RECDES` 바이트가 필요한 경로만 `heap_get_visible_version_expand_oos` 로 **Expand** 를 opt-in 한다.
- **UPDATE 체인 재사용 및 소유권 불변식 (`CBRD-27230`)**: UPDATE 문에서 **할당되지 않은** OOS 속성은 기존 24B 스터브를 그대로 재사용한다. 각 OOS 값 체인은 그것을 참조하는 최신 논리 레코드 버전이 소유하고, 이전 버전의 undo 이미지는 읽기·롤백용 차용 참조만 보유하며 절대 삭제 원천으로 쓰지 않는다. 버려진 체인은 커밋 후 postpone이 발행하는 `RVOOS_NOTIFY_VACUUM` 을 vacuum이 소비할 때 1회만 회수한다.

### §4. 복구·HA·Vacuum·빈 페이지 회수

- **복구와 복제 불변식**: 마스터의 물리 OOS OID를 복제본에 그대로 쓰지 않고 복제본이 자체 `oos_insert` 및 재사용 마커 보정으로 값 동등성을 유지한다. `DELETE` 는 MVCC 모드에서 스터브·체인을 보존하고, SA/비MVCC eager 경로만 커밋 시점에 회수 의도(reclaim intent)를 실행한다.
- **확정 후 redo-only 회수 (`OOS-ADR-0008`)**: 청크 삭제(`RVOOS_DELETE`)에는 undo가 없다. REMOVE(sysop 커밋 후), UPDATE 알림(vacuum 소비 후), eager 정리(트랜잭션 커밋 후) 모두 회수 의도(`(OOS VFID, head OOS OID, head stamp)`)를 postpone으로 기록하고, 확정된 뒤에야 tail-first reclaimer가 redo-only로 삭제한다. 실패 시 fail-stop 정책으로 재시작 복구가 postpone을 재실행한다.
- **성장 전 빈 페이지 회수 불변식 (`CBRD-26786`, `OOS-ADR-0009`, `OOS-ADR-0010`)**: 완전히 빈 OOS 데이터 페이지는 파일이 쓰기 없이 유휴 상태일 때 반환할 의무는 없으나, 새 섹터를 예약하기 전에는 반드시 회수·재사용해야 한다. 이를 위해 파일별 `emptied-page set` (`OOS_BESTSPACE_CACHE` bestspace mutex 보호, 성장 잠금과 연동)으로 빈 페이지를 추적해 `oos_alloc_page_with_reclaim` 에서 2단계 검증 후 회수하며, 재시작·오버플로로 집합이 불완전할 때는 sector-bitmap lap 1회로 복구한다.

### §5. 생명주기·TDE·11.5 릴리스 범위 및 용어

- **DROP·TDE·LOB (`CBRD-26608`, `CBRD-26830`, `OOS-ADR-0002`)**: `DROP TABLE` 시 `oos_remove_file` 로 OOS 파일을 제거한다. TDE 테이블은 OOS VFID를 힙 헤더에 공개하기 전에 암호화를 적용한다. BLOB/CLOB는 88B 수준 locator 바이트만 OOS로 이동하며 외부 LOB 파일 수명 관리는 LOB 계층에 남는다.
- **11.5 병합 CDC 유예 및 부트 포맷 검사 (`OOS-ADR-0005`, `0006`, `0007`)**: 디스크 호환성 `11.5` 를 유지하고 `CBRD-26939` (CDC/flashback용 OOS 보강 이미지)는 11.5 병합에서 유예했다(`cbrd_27064`, `cbrd_27075` 는 QA 회귀에서만 실행). 대신 `disk_format()` 이 볼륨 헤더 `storage_format` 필드에 `DISK_STORAGE_FORMAT_REVISION = 1` 을 기록하고 부트·`patchdb` 에서 일치 여부를 검사해 스탬프 이전 DB를 `ER_BO_INCOMPATIBLE_STORAGE_FORMAT` 으로 거부한다.
- **핵심 용어 (`OOS-CONTEXT.md` & `CONTEXT.md`)**: `OOS inline stub` (24B 전체 구조), `OOS value chain` (청크 연결 리스트), `OOS Expand` (레코드 단위) / `OOS Resolve` (속성 단위) / `OOS Read` (저장소 단위), `Reclaim intent` (커밋 후 회수 의도), `OOS reclaimer` (redo-only 재실행 회수기), `Emptied-page set` (빈 페이지 집합), `Supported / Legacy OOS history` (CDC 이력 재구성 보장 여부 구분).

## Architecture Decision Records (OOS-ADR-0001 ~ OOS-ADR-0011)

사내에서 각 결정을 인용할 때는 아래 `OOS-ADR-NNNN` 식별자를 사용한다. **주의**: `OOS-ADR-0001`~`0010` 만 현재 `accepted` 상태이며, `OOS-ADR-0011` 은 `proposed` 상태로서 확정 규범이 아니다.

| ID | 상태 | Last updated | 제목 및 핵심 결정 | 개정·대체 관계 | 관련 CBRD | 원문(GitHub) |
| --- | --- | --- | --- | --- | --- | --- |
| `OOS-ADR-0001` | `accepted` | `2026-06-18` | `FILE_OOS` 를 비순번(non-numerable) 영구 파일로 전환하고 sector-bitmap walk로 열거 | - | `CBRD-26831`, `CBRD-26786` | [0001](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0001-oos-page-enumeration-non-numerable.md) |
| `OOS-ADR-0002` | `accepted` | `2026-07-13` | BLOB/CLOB locator 컬럼도 일반 가변 타입과 동일하게 OOS demotion 대상 유지 | - | `CBRD-26814` | [0002](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0002-oos-lob-locator-demotion.md) |
| `OOS-ADR-0003` | `accepted` | `2026-07-13` | OOS 레코드 Expand는 원시 바이트 소비자 전용 opt-in 계약으로 유지 | - | `CBRD-26847`, `CBRD-26948` | [0003](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0003-oos-expansion-is-opt-in.md) |
| `OOS-ADR-0004` | `accepted` | `2026-09-22` | CDC/flashback 이력 보존을 위한 supplemental WAL 보강 이미지 방향 | `OOS-ADR-0005` 에 의해 11.5 활성화·호환 계약 일부 대체(재설계 필요) | `CBRD-26939` | [0004](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0004-durable-oos-supplemental-images.md) |
| `OOS-ADR-0005` | `accepted` | `2026-10-27` | 11.5 병합에서 OOS CDC/flashback 이력 변경 전면 유예, 디스크 레벨 11.5 유지 | `OOS-ADR-0004` 일부 대체; `OOS-ADR-0006` 개정·`OOS-ADR-0007` 테스트 정책 일부 대체 | `CBRD-26939`, `CBRD-26357` | [0005](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0005-defer-oos-history-from-the-11-5-merge.md) |
| `OOS-ADR-0006` | `accepted` | `2026-11-05` | 볼륨 헤더 `storage_format` 스탬프(1)로 부트 시 사전 스탬프 DB 거부 | `OOS-ADR-0005` 개정; `OOS-ADR-0008` 에 의해 병합 전 변경 리비전 1 유지 개정 | `CBRD-26357` | [0006](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0006-reject-pre-stamp-databases-at-boot.md) |
| `OOS-ADR-0007` | `accepted` | `2026-10-27` | 유예된 CDC 회귀(`cbrd_27064`, `27075`)는 `develop` CI에서 빼고 QA 회귀에서만 실행 | `OOS-ADR-0005` 의 테스트 정책 일부 대체 | `CBRD-26939` | [0007](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0007-run-deferred-cdc-regressions-in-qa-regression-only.md) |
| `OOS-ADR-0008` | `accepted` | `2026-11-12` | 삭제 확정 뒤에만 postpone·redo-only reclaimer(32B 링크 스탬프·fail-stop)로 체인 회수 | `OOS-CONTEXT.md` §2~§4·`OOS-ADR-0006` 개정, LSA gate 제거 | `CBRD-27781`, `CBRD-27237` | [0008](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0008-reclaim-oos-chains-after-the-delete-is-final.md) |
| `OOS-ADR-0009` | `accepted` | `2026-11-06` | 빈 OOS 페이지는 유휴 시 반환하지 않고 다음 파일 성장 전에만 회수·재사용 보장 | `OOS-CONTEXT.md` §4 빈 페이지 불변식 개정 | `CBRD-27925`, `CBRD-26786` | [0009](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0009-reclaim-empty-pages-before-growth-not-while-idle.md) |
| `OOS-ADR-0010` | `accepted` | `2026-11-09` | 청크 삭제 카운터 대신 파일별 `emptied-page set` 으로 성장 게이트 회수 트리거 | `OOS-CONTEXT.md` §4 성장 게이트 개정(`RVOOS_INSERT` 8B VFID undo 추가) | `CBRD-27925`, `CBRD-27872` | [0010](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0010-arm-growth-reclaim-with-emptied-pages.md) |
| `OOS-ADR-0011` | `proposed` | `2026-11-11` | 빈 OOS 페이지를 dealloc/fast path 없이 제자리에서 재사용(미확정 제안) | 채택 시 `OOS-ADR-0009` 결정 3·`OOS-ADR-0010` 결정 3 개정 | `CBRD-28281`, `CBRD-27925` | [0011](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0011-reuse-emptied-pages-in-place.md) |

각 `OOS-ADR-NNNN` 의 상세 배경·검토한 대안·트레이드오프·결과 요약은 본 이슈의 `OOS-ADR-NNNN` 댓글로 1:1 동기화한다.

## Non-Normative Reference Documents

아래 문서는 규범 명세가 아니며, 배경 이해·과거 관측 확인·테스트 작성 참고용으로만 사용한다.

| 문서 | Last updated | 역할 및 범위 | 주의사항 | 원문(GitHub) |
| --- | --- | --- | --- | --- |
| `design-history.md` | `2026-11-09` | M1 규칙, PG TOAST/MySQL 비교, ADR-0008 이전 회수 규칙, 유예된 최적화 논의 이력 | 이미 대체된 과거 규칙이 포함되므로 현재 규범으로 오인 금지 | [design-history.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/reference/design-history.md) |
| `implementation-observations.md` | `2026-11-19` | 이슈별 구현·검증 관측 스냅샷(`CBRD-26950`, `27230`, `27237`, `28062`, `ADR-0008` 등) | 상당수가 `PR #7990` 병합 전 커밋 기준이므로 현재 상태는 코드·JIRA로 재확인 필요 | [implementation-observations.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/reference/implementation-observations.md) |
| `test-recipes.md` | `2026-10-27` | `BIT VARYING` 테스트 패턴, demotion 계산 예시, 카테고리별 시나리오 | §9.6에 `bigone` 개정(2026-11-09 비시스템 클래스 거부) 이전 문구가 남아 있어 원본 보정 예정 | [test-recipes.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/reference/test-recipes.md) |

## Sync Maintenance and Related Work

### 동기화 유지보수 절차

1. `cubrid-oos-context` (`main`)에서 `OOS-CONTEXT.md` 또는 `docs/adr/NNNN-*.md` 를 추가·수정하고, 비공개 로컬 경로나 개인 작업 ID가 없는지 확인한다.
2. 동기화 매니페스트(`docs/maintenance/jira-sync-manifest.json`)를 대조해 변경된 Spec/ADR을 식별한다.
3. 본 JIRA 이슈의 마스터 인덱스 표·규범 요약을 갱신하고, 추가·수정된 `OOS-ADR-NNNN` 에 대응하는 댓글을 생성 또는 제자리 수정한다.

### Related Work

- [CBRD-26357](https://jira.cubrid.org/browse/CBRD-26357): OOS 도입 Epic (부모 이슈, `PR #7990` 병합 완료)
- [CBRD-26978](https://jira.cubrid.org/browse/CBRD-26978): OOS TODO Epic (연계 후속 Epic)
- [CBRD-28281](https://jira.cubrid.org/browse/CBRD-28281): `OOS-ADR-0011` (빈 페이지 제자리 재사용, `proposed`) 채택 여부 결정 이슈
- [CBRD-26592](https://jira.cubrid.org/browse/CBRD-26592): 과거 M1 시점 PG TOAST vs OOS 스펙 비교표 (`Closed / Won't Fix`)
- 핵심 설계 결정 연계 이슈: [CBRD-26950](https://jira.cubrid.org/browse/CBRD-26950), [CBRD-27230](https://jira.cubrid.org/browse/CBRD-27230), [CBRD-27781](https://jira.cubrid.org/browse/CBRD-27781), [CBRD-27925](https://jira.cubrid.org/browse/CBRD-27925), [CBRD-28062](https://jira.cubrid.org/browse/CBRD-28062)
