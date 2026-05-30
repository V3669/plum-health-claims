# Eval Report — Plum Claims Processing System

Generated: 2026-05-30T08:10:40.784949+00:00
**12/12 test cases passed.**

| Case ID | Case Name | Expected | Actual | Amount | Confidence | Match | Notes |
|---------|-----------|----------|--------|--------|-----------|-------|-------|
| TC001 | Wrong Document Uploaded | HALTED | HALTED | — | 0.00 | ✓ | Correctly halted before decision |
| TC002 | Unreadable Document | HALTED | HALTED | — | 0.00 | ✓ | Correctly halted before decision |
| TC003 | Documents Belong to Different Patients | HALTED | HALTED | — | 0.00 | ✓ | Correctly halted before decision |
| TC004 | Clean Consultation â€” Full Approval | APPROVED | APPROVED | ₹1350.00 | 0.95 | ✓ | All assertions passed |
| TC005 | Waiting Period â€” Diabetes | REJECTED | REJECTED | — | 0.95 | ✓ | All assertions passed |
| TC006 | Dental Partial Approval â€” Cosmetic Exclusion | PARTIAL | PARTIAL | ₹8000.00 | 0.95 | ✓ | All assertions passed |
| TC007 | MRI Without Pre-Authorization | REJECTED | REJECTED | — | 0.95 | ✓ | All assertions passed |
| TC008 | Per-Claim Limit Exceeded | REJECTED | REJECTED | — | 0.95 | ✓ | All assertions passed |
| TC009 | Fraud Signal â€” Multiple Same-Day Claims | MANUAL_REVIEW | MANUAL_REVIEW | — | 0.95 | ✓ | All assertions passed |
| TC010 | Network Hospital â€” Discount Applied | APPROVED | APPROVED | ₹3240.00 | 0.95 | ✓ | All assertions passed |
| TC011 | Component Failure â€” Graceful Degradation | APPROVED | APPROVED | ₹4000.00 | 0.67 | ✓ | All assertions passed |
| TC012 | Excluded Treatment | REJECTED | REJECTED | — | 0.95 | ✓ | All assertions passed |

## Notes

- TC001–TC003 produce `HALTED` decisions (early gate failures), not `null`.
- TC004 approved amount ₹1350 = ₹1500 − 10% co-pay.
- TC006 partial approval ₹8000; Teeth Whitening (₹4000) excluded as cosmetic.
- TC010 approved amount ₹3240 = ₹4500 × 80% (network) × 90% (co-pay).
- TC011 confidence is reduced due to degraded policy evaluation stage.
- TC012 bariatric exclusion detected from diagnosis + treatment text.