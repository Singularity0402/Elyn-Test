/* 수집 시작 전 확정. 해시/설계를 바꾼 수집은 새 protocol_id를 사용한다. */
globalThis.OBSERVER_PROTOCOL = Object.freeze({
  protocol_id: 'hetbahn-audit-2026-11-03-pilot-v1',
  schema_version: 1,
  hash_status: 'final_audit_2026-11-03',
  hash_note: '주세션이 확정한 audit_2026-11-03 A6/B 수정본의 SHA256.',
  images: Object.freeze({
    A: Object.freeze({path: '../A_갓지은편지.png', sha256: '5544cfeb3ed3b3b0638a43b35049dda1faee6dc8f7043ab955255f5847946e1b'}),
    B: Object.freeze({path: '../B_스물네장의계절.png', sha256: '1df49d188cb60fec5f27a29c79e6060153cb5803a5655e61eaaf8600a5ec95c4'})
  }),
  assignment_method: 'Python SystemRandom.shuffle, six A and six B, one draw fixed before real collection',
  // A 6개/B 6개를 한 번 무작위 섞은 뒤 고정. 브라우저에서 다시 추첨하지 않는다.
  assignment: Object.freeze({P01:'B', P02:'A', P03:'A', P04:'A', P05:'B', P06:'A', P07:'A', P08:'A', P09:'B', P10:'B', P11:'B', P12:'B'}),
  target_exposure_ms: 3000,
  valid_exposure_ms: Object.freeze([2800, 3800]),
  recall_delay_ms: 24 * 60 * 60 * 1000,
  sample_size: 12,
  per_arm: 6,
  internal_goal: '각 안 5/6은 내부 제작 목표이며 통계적 보장이나 유의성 기준이 아니다.',
  comparison_scope: 'A/B 파일럿의 동등 노출 비교. 미확인 L06을 실제 경쟁작 필수 기준으로 해석하지 않으며 경쟁대회 우위를 주장하지 않는다.'
});
