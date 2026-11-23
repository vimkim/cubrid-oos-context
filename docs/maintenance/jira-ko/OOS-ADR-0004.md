## OOS-ADR-0004: CDC 및 flashback 이력 보존을 위한 supplemental WAL 보강 이미지 방향

- **원제**: Preserve OOS historical values in supplemental images
- **상태**: `accepted` (단, `OOS-ADR-0005` 에 의해 11.5 병합에서 활성화·호환성 계약 일부 대체)
- **Last updated**: `2026-09-22`
- **개정·대체 관계**: `OOS-ADR-0005` (2026-09-22)에 의해 11.5 병합 범위에서 유예되고 활성화/호환성 계약이 일부 대체됨(향후 재설계 필요)
- **관련 CBRD**: [CBRD-26939](https://jira.cubrid.org/browse/CBRD-26939)
- **원문(GitHub SoT)**: [docs/adr/0004-durable-oos-supplemental-images.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0004-durable-oos-supplemental-images.md) (기준 커밋 `139ec89`)

### 배경

vacuum이 이미 회수한 OOS 값 체인에 대해 CDC와 flashback 이력 조회가 변경 전/후(before/after) 논리 값을 재구성하지 못하는 문제가 `CBRD-26939` 에서 확인되었다.

### 결정

1. OOS 속성을 포함한 변경의 supplemental WAL에는 확장된 전체 논리 이미지(complete expanded images)를 기록해, 이력 소비자가 OOS 체인 생존 여부와 무관하게 재구성할 수 있도록 하는 **후보 방향**을 채택한다(2026-09-08 합의).
2. 구현 시 새로 기록되는 OOS 이력은 보장하고, 재구성할 수 없는 기존(legacy) OOS 이력은 값 추측·건너뛰기 없이 명시적 오류를 반환한다.
3. 필요한 supplemental 이미지 구성·기록이 실패하면 정상 롤백 처리로 원본 쓰기를 실패시킨다.

### 검토한 대안

- **이력 소비자를 위해 OOS 체인을 장기 보존**: 지연되거나 연결이 끊긴 CDC/flashback 소비자까지 고려한 보존 기준선과 공간 증가·복구 부담이 커서 기각.
- **Supplemental WAL 보강 이미지 (채택 방향)**: supplemental 로깅 활성 시 직렬화와 WAL 용량을 감수하는 대신 이력 읽기와 OOS 회수 수명을 분리.

### 결과 및 영향

- 이후 `OOS-ADR-0005` (2026-09-22)가 11.5 OOS 병합에서 `CBRD-26939` 전체를 유예하면서, 이 ADR에 함께 적혔던 "11.6 호환성 레벨 도입 및 오프라인 단방향 활성화" 계약은 철회되었다.
- 따라서 본 ADR의 내구 이미지 방향과 분석 근거는 향후 `CBRD-26939` 구현의 참고 기반으로만 남으며, 인코딩·공개 순서·리더 오류 처리·호환성 강제 방식은 실제 릴리스 모델에 맞춰 재설계가 필요하다.
