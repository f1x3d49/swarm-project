# Phase 1

## Questions

1. Synchronization sqew across swarm: Am  trimis comenzile la un interval de cateva ms, dar dronele s-au ridicat la un interval de 1s fiecare. Posibil sa fie din cauza logului sau chiar sa fie o problema.

 500 cm/s   mean error  10.99 m   (formation_500_185715.csv)
 250 cm/s   mean error  10.98 m   (formation_250_190050.csv)
 125 cm/s   mean error  12.29 m   (formation_125_193536.csv)

 Original data lost
 Original data buggy due to the script telling the drones that they should follow the leader at a certain distance west and east of the drone. But those coordinates always point north, so when the leader was on the side of the square that was north he was facing south, but the drones that should follow don't know that so they always position to the absolute west and east of the leader.


## Formation control — heading rotation fix (verified)
- Original bug: fixed north/east offsets produced heading-dependent error that never converged.
- Fix: rotate offset into leader's body frame using GLOBAL_POSITION_INT.hdg.
- Side effect: rotating a long offset arm (~15.6m) through a turn creates a target
  discontinuity proportional to arm length x turn rate. Measured peak: ~18.6 deg
  per 5Hz tick (~93 deg/s), giving ~5m target jump during sharp corners.
  Wraparound at 0/360 must be corrected before diffing heading (mod 360, centered).
- Next: re-measure mean formation error post-fix (expect flat vs heading, not
  oscillating); consider low-pass filtering the offset vector to smooth corner
  transients if needed.
