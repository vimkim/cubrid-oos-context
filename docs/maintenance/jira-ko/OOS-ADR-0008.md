## OOS-ADR-0008: 삭제 확정 뒤에만 postpone과 redo-only reclaimer로 OOS 체인 회수

- **원제**: Reclaim OOS chains only after the delete is final
- **상태**: `accepted`
- **Last updated**: `2026-11-12`
- **개정·대체 관계**: `OOS-CONTEXT.md` §2·§3·§4 및 `OOS-ADR-0006` 개정; 기존 커밋 훅 기반 `RVOOS_NOTIFY_VACUUM` 배치 및 LSA reclaim gate 대체
- **관련 CBRD**: [CBRD-27781](https://jira.cubrid.org/browse/CBRD-27781), [CBRD-27237](https://jira.cubrid.org/browse/CBRD-27237)
- **원문(GitHub SoT)**: [docs/adr/0008-reclaim-oos-chains-after-the-delete-is-final.md](https://github.com/vimkim/cubrid-oos-context/blob/main/docs/adr/0008-reclaim-oos-chains-after-the-delete-is-final.md) (기준 커밋 `139ec89`)

### 배경

TLA+ 설계 모델링과 분석에서 세 가지 데이터 손상/유실 결함이 확인되었다: (1) `CBRD-27858`, `CBRD-27781` — vacuum sysop이 청크 슬롯을 지운 뒤 다른 트랜잭션이 그 슬롯을 재사용하면 `log_sysop_abort` 나 재시작 undo가 `spage_insert_for_recovery` 로 덮어쓰는 문제, (2) `CBRD-27237` — forward-walk가 커밋/중단 여부를 모른 채 UPDATE undo 이미지의 체인을 지워 롤백된 UPDATE의 살아있는 체인을 삭제하는 문제, (3) `CBRD-26950` (이미 신원 스탬프로 해결). 2026-11-05 팀 리드 승인으로 확정되었다(`CBRD-27858` 힙 forward 슬롯은 별도 수정 범위).

### 결정

1. **청크 삭제는 undo하지 않는다(D3)**: REMOVE sysop이나 SA/비MVCC eager 정리는 청크를 즉시 지우는 대신 **회수 의도(reclaim intent)** `(OOS VFID, head OOS OID, head stamp)` 를 postpone으로 남기고, 커밋된 뒤 **OOS reclaimer** 가 redo-only 로그(`RVOOS_DELETE`)로 삭제한다. 해제된 슬롯은 즉시 재사용 가능하다.
2. **Postpone 기반 UPDATE 알림(A', B3 대비 채택)**: UPDATE는 버린 체인을 postpone으로 기록(문장/세이브포인트 롤백 시 취소)하고, `LOG_COMMIT_WITH_POSTPONE` 이후에 UPDATE의 명시적 MVCCID를 실은 `RVOOS_NOTIFY_VACUUM` 을 기록한다. vacuum은 해당 MVCCID보다 오래된 활성 스냅샷이 없을 때만 reclaimer를 실행한다. 기존 undo-image forward-walk는 제거한다.
3. **재실행 수렴 reclaimer 및 fail-stop**: reclaimer는 head부터 스탬프를 확인해 어긋나거나 없는 슬롯에서 멈추고 tail부터 head 순으로 삭제하며, 오류/크래시 후 head부터 재실행한다. 확정된 회수 의도 실패 시 완료 처리하지 않고 서버를 중지(fail-stop)해 재시작 복구가 postpone을 재실행하게 한다(단, vacuum 알림 소비자의 `ER_INTERRUPTED` 종료 인터럽트는 예외).
4. **32B 청크 헤더**: next-chunk OID 옆에 **next-chunk identity stamp** 를 함께 저장(헤더 24B → 32B)해 재실행 시 중간 슬롯 재사용으로 인한 오삭제를 막는다.
5. **LSA reclaim gate 제거**: 청크 삭제 undo가 사라졌으므로 빈 페이지 반납을 막던 LSA gate를 제거한다.
6. **병합 전 포맷 변경 리비전 1 유지 및 성능 검증 조건(결정 7)**: `PR #7990` 전 변경이므로 `DISK_STORAGE_FORMAT_REVISION` 은 1을 유지하고, 회수 로그량·vacuum 처리량·단일/동시 INSERT·UPDATE 지연이 기존 구현보다 나빠지지 않아야 병합한다(`CUBRID/cubrid#8495` 와 함께 조건 충족 확인, 2026-11-12).

### 검토한 대안

- **undoable 삭제 보호**: D1(모든 페이지 래치 유지 → 교착), D2a(슬롯 번호만 보호 → `SP_DOESNT_FIT` 실패), D2b/D2c(바이트 예약/페이지 폐쇄 → 복잡도 및 2PC 부담) 모두 TLC/구조 비교에서 D3(no-undo + postpone)보다 불리.
- **UPDATE 드롭 결정**: B3(head에 undoable delete MVCCID 기록)는 TLC에서 통과했으나 head 쓰기 1회 + 8B 필드 + 추가 복구 인덱스가 필요해 팀 리드 결정으로 A'(postpone 알림) 채택. B2(체인 먼저 회수 후 힙 삭제)는 스냅샷 없는 리더(`btree_load`)가 끊긴 체인을 읽어 `ER_HEAP_OOS_CORRUPTED_RECORD` 실패로 기각.
- **저장 레이아웃 C1~C4**: 페이지당 1체인(24B 초과 값도 1페이지 낭비), 재삽입 금지, 논리 ID 맵, 제자리 덮어쓰기 모두 공간·성능 비용으로 기각.

### 결과 및 영향

- `RVOOS_DELETE` 가 redo-only로 바뀌고, `RVOOS_NOTIFY_VACUUM` 발행/소비자 및 논리 postpone(`RVOOS_RECLAIM_POSTPONE`, `RVOOS_UPDATE_DROP_POSTPONE`)이 추가되며 `RVHF_DELETE_NEWHOME_NOTIFY_VACUUM` 은 제거된다.
- 6,000B 값당 회수 로그가 약 6.1KB에서 약 0.71KB로 감소했다(2026-11-05 측정).
- 단순성을 위해 채택한 fail-stop 정책은 영구적인 회수 오류 시 재시작까지 막을 수 있는 가용성 트레이드오프를 가지며, `LOG_COMMIT_WITH_POSTPONE` 과 `LOG_COMMIT` 사이 정지 시 복제 레코드가 누락되는 기존 창(consequence 8)을 명시적으로 인지하고 사용한다.
