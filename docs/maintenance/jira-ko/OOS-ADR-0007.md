## OOS-ADR-0007: 유예된 CDC 회귀 테스트의 develop CI 제외 및 QA 회귀 전용 실행

- **원제**: Run the deferred-CDC regressions in QA regression only, not develop CI
- **상태**: `accepted`
- **Last updated**: `2026-10-27`
- **개정·대체 관계**: `OOS-ADR-0005` 의 테스트 정책(CI에서 실패 상태로 유지) 일부 대체
- **관련 CBRD**: [CBRD-26939](https://jira.cubrid.org/browse/CBRD-26939)
- **원문(GitHub SoT)**: [docs/adr/0007-run-deferred-cdc-regressions-in-qa-regression-only.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0007-run-deferred-cdc-regressions-in-qa-regression-only.md) (기준 커밋 `139ec89`)

### 배경

`OOS-ADR-0005` 는 `CBRD-26939` 공백을 드러내기 위해 `cbrd_27064` 와 `cbrd_27075` 를 CI에 활성·실패 상태로 두려 했으나, `PR #7990` 이 `develop` 에 병합되면 모든 `develop` PR의 `gha-ci` `test_shell` 결과에 동일한 두 건의 알려진 실패가 상시 나타나게 된다. 2026-10-27 `PR #7990` 리뷰 질문에 따라 QA팀과 합의했다.

### 결정

1. `cbrd_27064` 와 `cbrd_27075` 는 `develop` CI에서 제외한다(private-ex `PR #4210` 에서 `gha-ci` 가 제외하는 `shell/_25_unstable/_37_elderberry/cbrd_23842_cdc/bug/` 로 이동).
2. 두 테스트는 **QA 회귀**에서는 계속 실행하여 실패가 가시적으로 남게 하며, 기대 결과를 고치거나 실패를 가리지 않는다.
3. OOS + CDC 지원은 `CBRD-26939` 에서 별도로 구현하며 그전까지 두 테스트가 미지원 공백을 기록한다.

### 검토한 대안

- **PR CI에 실패 상태로 계속 포함 (`OOS-ADR-0005` 초기안)**: 모든 `develop` PR의 CI 신호를 오염시켜 기각.
- **기대값 수정 또는 테스트 삭제**: 유예된 기능 공백을 숨기게 되어 기각.
- **QA 회귀 전용 실행 (채택)**: `develop` PR CI의 신호 선명도를 지키면서 QA 회귀에서 미지원 상태를 계속 추적.

### 결과 및 영향

- `CBRD-26939` 반영 전까지 `develop` 은 OOS 속성을 포함한 행의 UPDATE/DELETE 시 CDC 추출 오류(`rc=-10`) 공백을 갖는다.
- `gha-ci` 통과가 이 두 CDC 케이스 통과를 뜻하지 않으며, OOS CDC 회귀 판정은 QA 회귀 결과를 기준으로 한다.
- `_25_unstable` 규칙에 따라 추후 연속 5회 통과 시 원래 디렉터리로 복귀할 수 있다.
