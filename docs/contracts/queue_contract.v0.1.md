# Queue Contract v0.1

**Status:** Frozen (post GS-002). Queue semantics are a core experimental knob for fairness vs. latency vs. safety; this contract must not be weakened by later work.

---

## 1. Device queue item fields

Each item in a per-device queue is a **device queue item** with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `work_id` | `str` | Canonical identifier for the work unit. In v0.1 this is the specimen_id (or resolved from accession_id / aliquot_id). Later may be rack_id or run_id. |
| `priority_class` | `"STAT"` \| `"URGENT"` \| `"ROUTINE"` | Priority class used for ordering. |
| `enqueued_ts_s` | `int` | Simulation time (seconds) at which the item was enqueued. |
| `requested_by_agent` | `str` | Agent id that requested the QUEUE_RUN (for audit). |
| `reason_code` | `str` \| `null` | Optional reason code for audit; recommended when strict reason-codes mode is on. |
| *(internal)* `tie_break` | `int` | Monotonic counter assigned by the queue store for stable ordering when priority and time are equal. |

---

## 2. Priority ordering rule

Queues are **deterministically ordered**. The head of the queue is the item that compares smallest under the following rule (in order):

1. **Primary key:** `priority_rank(priority_class)`  
   - `STAT` = 0  
   - `URGENT` = 1  
   - `ROUTINE` = 2  
   - Any other value = 99 (lowest priority).

2. **Secondary key:** `enqueued_ts_s` (ascending: earlier enqueue → earlier in queue within same priority).

3. **Tertiary key:** `tie_break` (ascending: monotonic counter per device queue; stable tie-break when priority and time are equal).

So: **STAT always precedes URGENT and ROUTINE**; within the same priority class, FIFO by enqueue time, then by insertion order. This yields the “STAT jumps to front” behavior required by GS-002 without ad-hoc logic.

---

## 3. QUEUE_RUN semantics

- **Action:** `QUEUE_RUN`
- **Effect:** Append one item to the queue for the given device, then re-sort by the ordering rule above.

**Args (minimal):**

- `device_id` (required): Must be a device present in the zone layout’s `device_placement` (device registry v0.1). Unknown device → BLOCKED, reason code `RC_DEVICE_UNKNOWN`.
- Work identifier (one of): `work_id`, `specimen_id`, first element of `accession_ids`, or first element of `aliquot_ids` (aliquot resolved to specimen_id when possible). Missing both device_id and work id → BLOCKED, reason code `RC_QUEUE_BAD_PAYLOAD`.
- `priority` or `priority_class` (optional): Default `ROUTINE`. Must be one of `STAT`, `URGENT`, `ROUTINE`.

**Other rules:**

- Co-location: the acting agent must be in the same zone as the device (same as other device actions); otherwise BLOCKED with `RC_DEVICE_NOT_COLOCATED`.
- Duplicate `work_id` per device: v0.1 allows duplicates (`allow_duplicate_work_id=True`). If a future version disallows them, BLOCKED with `RC_QUEUE_DUPLICATE_WORK_ID`.

**On ACCEPTED:** Emit `QUEUE_RUN`. Event is appended to the audit log.

---

## 4. START_RUN and queue interaction

START_RUN may obtain the work to run from the queue or from explicit args. Interaction is defined as follows.

**Case A — No explicit work:**  
`START_RUN` has `device_id` and **no** `work_id`, `specimen_ids`, or `aliquot_ids`.

- The engine **consumes the head** of that device’s queue.
- If the queue is **empty** → BLOCKED, reason code `RC_QUEUE_EMPTY`.
- Otherwise, the consumed `work_id` is used as the work unit for the run (e.g. specimen_ids = [consumed_work_id]) and the rest of START_RUN (stability, co-location, etc.) proceeds.

**Case B — Explicit work:**  
`START_RUN` has `device_id` and at least one of `work_id`, `specimen_ids`, or `aliquot_ids`.

- Resolve to a single **expected work_id** (e.g. first specimen_id from resolved specimen_ids or aliquot_ids, or explicit work_id).
- Let `head = queue_head(device_id)`.
- If `head` is not None and `head != expected_work_id` → BLOCKED, reason code `RC_QUEUE_HEAD_MISMATCH` (strict “factory line” semantics: must run the head of the queue).
- If `head == expected_work_id`, the engine **consumes the head** and proceeds with START_RUN (stability, co-location, QC registration, etc.).

So: **queue head is consumed exactly when START_RUN is accepted** for that device, either by taking the head as the work (Case A) or by matching the head to the explicit work (Case B).

---

## 5. Meaning of `queue_head(device_id)`

- **Query:** `queue_head(DEVICE_ID)`  
  Example: `queue_head(DEV_CHEM_A_01)`.

- **Returns:** The `work_id` of the item at the **front** of that device’s queue after the ordering rule (Section 2), or `None` if the queue is empty or the device is unknown.

- **Use:** State assertions in the golden suite (e.g. GS-002) and by policies or agents to decide what work is next. No side effects; read-only.

---

## 6. Version and stability

- **Contract version:** 0.1  
- **Frozen:** After GS-002 (STAT insertion, `queue_head(DEV_CHEM_A_01) == 'S2'`) is green.  
- **Later work:** May add options (e.g. fairness vs. latency vs. safety knobs, duplicate-work-id policy, or out-of-order start with violation) but must **not** weaken or contradict this contract without a version bump and changelog.
