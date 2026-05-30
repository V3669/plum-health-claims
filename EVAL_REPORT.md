# Eval Report — Plum Claims Processing System

Generated: 2026-05-30T10:55:34.951862+00:00
**12/12 test cases passed.**

## Summary

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

---

## Per-Case Detail & Traces

### TC001: Wrong Document Uploaded

**Result:** PASS ✓  
**Decision:** `HALTED`  **Expected:** `HALTED`  **Amount:** —  **Confidence:** 0.00  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | FAIL | 0.00 | Required document types not uploaded. |

*Halt:* `DOCUMENT_TYPE_MISMATCH` — Your consultation claim requires the following documents: prescription, hospital bill. You uploaded: 2 prescription(s). Please upload the missing document(s): hospital bill and resubmit. You do not need to re-upload the documents that are already correct.

### TC002: Unreadable Document

**Result:** PASS ✓  
**Decision:** `HALTED`  **Expected:** `HALTED`  **Amount:** —  **Confidence:** 0.00  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | FAIL | 0.00 | Document unreadable: prescription.jpg |

*Halt:* `DOCUMENT_UNREADABLE` — We could not read this document: 'prescription.jpg' (declared as prescription). Please upload a clearer photo or PDF of this specific document. All other documents in your claim are fine — only re-upload the one named here.

### TC003: Documents Belong to Different Patients

**Result:** PASS ✓  
**Decision:** `HALTED`  **Expected:** `HALTED`  **Amount:** —  **Confidence:** 0.00  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.70 | Extracted 2 document(s). |
| ConsistencyCheck | FAIL | 0.00 | Patient name mismatch detected. |

*Halt:* `PATIENT_NAME_MISMATCH` — The documents in this claim appear to belong to different patients. We found: 'Rajesh Kumar' on file 'F005'; 'Arjun Mehta' on file 'F006'. Please verify the documents and resubmit with documents belonging to the same patient.

### TC004: Clean Consultation â€” Full Approval

**Result:** PASS ✓  
**Decision:** `APPROVED`  **Expected:** `APPROVED`  **Amount:** ₹1350.00  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 2 document(s). |
| ConsistencyCheck | PASS | 1.00 | Patient name consistent across documents. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: APPROVED, Amount: ₹1350.00 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Financial breakdown:*
- Claimed: ₹1500
- Co-pay: −₹150.00 → ₹1350.00
- **Approved: ₹1350.00**

### TC005: Waiting Period â€” Diabetes

**Result:** PASS ✓  
**Decision:** `REJECTED`  **Expected:** `REJECTED`  **Amount:** —  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 2 document(s). |
| ConsistencyCheck | PASS | 1.00 | Patient name consistent across documents. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: REJECTED, Amount: ₹0 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Rejection codes:* `WAITING_PERIOD`

### TC006: Dental Partial Approval â€” Cosmetic Exclusion

**Result:** PASS ✓  
**Decision:** `PARTIAL`  **Expected:** `PARTIAL`  **Amount:** ₹8000.00  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 1 document(s). |
| ConsistencyCheck | PASS | 1.00 | Patient name consistent across documents. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: PARTIAL, Amount: ₹8000.00 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Financial breakdown:*
- Claimed: ₹12000
- Excluded line items: −₹4000.00
- **Approved: ₹8000.00**

### TC007: MRI Without Pre-Authorization

**Result:** PASS ✓  
**Decision:** `REJECTED`  **Expected:** `REJECTED`  **Amount:** —  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 3 document(s). |
| ConsistencyCheck | PASS | 1.00 | No patient names in any document; cross-document name check skipped. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: REJECTED, Amount: ₹0 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Rejection codes:* `PRE_AUTH_MISSING`

### TC008: Per-Claim Limit Exceeded

**Result:** PASS ✓  
**Decision:** `REJECTED`  **Expected:** `REJECTED`  **Amount:** —  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 2 document(s). |
| ConsistencyCheck | PASS | 1.00 | No patient names in any document; cross-document name check skipped. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: REJECTED, Amount: ₹0 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Rejection codes:* `PER_CLAIM_EXCEEDED`

### TC009: Fraud Signal â€” Multiple Same-Day Claims

**Result:** PASS ✓  
**Decision:** `MANUAL_REVIEW`  **Expected:** `MANUAL_REVIEW`  **Amount:** —  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 2 document(s). |
| ConsistencyCheck | PASS | 1.00 | No patient names in any document; cross-document name check skipped. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: ['SAME_DAY_LIMIT'] |
| DecisionEngine | PASS | 1.00 | Decision: MANUAL_REVIEW, Amount: ₹0 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Fraud signals:* `SAME_DAY_LIMIT`

### TC010: Network Hospital â€” Discount Applied

**Result:** PASS ✓  
**Decision:** `APPROVED`  **Expected:** `APPROVED`  **Amount:** ₹3240.00  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 2 document(s). |
| ConsistencyCheck | PASS | 1.00 | Patient name consistent across documents. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: APPROVED, Amount: ₹3240.00 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Financial breakdown:*
- Claimed: ₹4500
- Network discount: −₹900.00 → ₹3600.00
- Co-pay: −₹360.00 → ₹3240.00
- **Approved: ₹3240.00**

### TC011: Component Failure â€” Graceful Degradation

**Result:** PASS ✓  
**Decision:** `APPROVED`  **Expected:** `APPROVED`  **Amount:** ₹4000.00  **Confidence:** 0.67  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 2 document(s). |
| ConsistencyCheck | PASS | 1.00 | No patient names in any document; cross-document name check skipped. |
| PolicyEvaluation | DEGRADED | 0.70 | Policy evaluation skipped due to simulated component failure. Using safe defaults. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: APPROVED, Amount: ₹4000.00 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Financial breakdown:*
- Claimed: ₹4000
- **Approved: ₹4000.00**

### TC012: Excluded Treatment

**Result:** PASS ✓  
**Decision:** `REJECTED`  **Expected:** `REJECTED`  **Amount:** —  **Confidence:** 0.95  

**Trace:**

| Stage | Status | Conf | Summary |
|-------|--------|------|---------|
| DocumentVerification | PASS | 1.00 | All required document types present. |
| DocumentExtraction | PASS | 0.95 | Extracted 2 document(s). |
| ConsistencyCheck | PASS | 1.00 | No patient names in any document; cross-document name check skipped. |
| PolicyEvaluation | PASS | 1.00 | Policy rules evaluated successfully. |
| FraudDetection | PASS | 1.00 | Fraud check complete. Signals: [] |
| DecisionEngine | PASS | 1.00 | Decision: REJECTED, Amount: ₹0 |
| Narrative | PASS | 1.00 | Narrative generated. |

*Rejection codes:* `EXCLUDED_CONDITION`
