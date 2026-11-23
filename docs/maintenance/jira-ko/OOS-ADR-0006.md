## OOS-ADR-0006: 볼륨 헤더 storage_format 스탬프로 부트 시 사전 스탬프 DB 거부

- **원제**: Reject pre-stamp databases at boot with a volume-header storage-format stamp
- **상태**: `accepted`
- **Last updated**: `2026-11-05`
- **개정·대체 관계**: `OOS-ADR-0005` 개정(엔진 검사 추가); `OOS-ADR-0008` 결정 6(2026-11-05)에 의해 병합 전 포맷 변경은 리비전 1 유지로 개정
- **관련 CBRD**: [CBRD-26357](https://jira.cubrid.org/browse/CBRD-26357)
- **원문(GitHub SoT)**: [docs/adr/0006-reject-pre-stamp-databases-at-boot.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0006-reject-pre-stamp-databases-at-boot.md) (기준 커밋 `139ec89`)

### 배경

`OOS-ADR-0005` 가 저장 포맷 변경 시 DB 재생성을 정책으로 정했으나 엔진 강제 검사가 없어, 기존 `develop` 나 구형 11.5 빌드가 만든 DB가 같은 디스크 호환성 레벨(`11.5`) 때문에 부트 검사를 통과한 뒤 페이지 타입 assert(디버그)나 헤더 오독(릴리스)을 일으켰다. `PR #7990` 리뷰 항목에 답하기 위해 2026-10-27 결정되었다.

### 결정

1. **볼륨 헤더 스탬프**: `disk_format()` 이 모든 포맷 볼륨의 `DISK_VOLUME_HEADER.storage_format` (기존 `reserved0`, 과거 11.x 빌드는 0 기록)에 `DISK_STORAGE_FORMAT_REVISION = 1` (OOS)을 1회 기록한다.
2. **부트·패치 시 조기 검사**: `boot_restart_server` 와 `xboot_emergency_patch` 가 볼륨 0을 마운트한 직후(DWB 및 로그 복구 전) 스탬프 일치를 검사하고, 다르면 `ER_BO_INCOMPATIBLE_STORAGE_FORMAT` 으로 거부한다.
3. **`deletedb` 예외**: 거부된 DB도 삭제할 수 있도록 `deletedb` (`boot_remove_all_volumes`)는 검사하지 않는다.
4. **페이지 타입 append-only**: `PAGE_OOS` 와 `PERF_PAGE_OOS` 를 enum 끝에 추가해 기존 `develop` 페이지 타입 번호를 보존하고 static assert 로 쌍을 맞춘다.

### 검토한 대안

- **볼륨 헤더 스탬프 (채택)**: 볼륨 0을 가장 먼저 읽으므로 구 DB를 훼손하지 않으며, 로그 재생성(`patchdb -r`, `copydb`)으로도 지워지지 않는다.
- **새 `disk_compatibility_level`**: `OOS-ADR-0005` 에 위배되며 GA 11.5가 11.5가 아닌 레벨을 갖게 되어 기각.
- **`SYSTEM_METADATA_VERSION` 증가**: 로그·vacuum 복구와 카탈로그 읽기 뒤에 검사하며 `upgradedb` 를 안내해 부적합하므로 기각.
- **로그 헤더 스탬프**: 로그 헤더 재생성 경로마다 현재 값이 덮어써져 마커가 지워지므로 기각.

### 결과 및 영향

- 스탬프 도입 전의 `develop`, QA daily, 구 OOS 브랜치 DB(남아 있는 `unittestdb` 포함)는 부트 시 거부되며, `deletedb` 후 재생성하거나 구 빌드로 unload 후 적재해야 한다.
- 검사는 단방향이므로 구 빌드는 스탬프가 찍힌 새 DB도 계속 열 수 있다(미출시 아티팩트 간 다운그레이드 미보장).
- 11.4 이하 릴리스 DB는 볼륨 0 마운트 전 기존 디스크 호환성 검사(`ER_LOG_INCOMPATIBLE_DATABASE` / `ER_LOG_BKUP_INCOMPATIBLE`)에서 먼저 거부된다.
