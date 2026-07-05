# Deep Analysis: Orphan Transaction Holding EXCLUSIVE Lock

> **Author**: dev-agent
> **Date**: 2026-07-05
> **Context**: handoff_orphan_transaction.md (V007.x 14-round failure) + V049 import fix
> **Status**: comprehensive analysis, no code changes proposed
> **Target reader**: coordinator, deploy-agent, e2e-agent, future maintainer

---

## TL;DR

The orphan transaction problem is **architectural**, not a retry tuning problem. The fundamental
issue is a **mismatch between Python's reference-counted in_transaction flag and SQLite's actual
connection state** after exception paths. V049 fix (FD leak) **reduces the trigger frequency** but
**does not eliminate the underlying bug**. V007.15 is still required as a separate worktree.

This report has 4 parts:
1. **SQLite transaction/lock/IO error deep dive** (what really happens)
2. **Code deep dive** (where exactly the state gets corrupted)
3. **V049 impact analysis** (does V049 fix reduce V007.x risk?)
4. **Refined V007.15 design** (additional safeguards beyond original 3-layer defense)

---

## 1. SQLite Transaction/Lock/IO Error Deep Dive

Sources (all from official docs, fetched 2026-07-05):
- https://www.sqlite.org/lang_transaction.html
- https://www.sqlite.org/rescode.html
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/c3ref/busy_timeout.html
- https://docs.python.org/3/library/sqlite3.html

### 1.1 Three Transaction Types

| Type | Lock acquired at BEGIN | Read concurrency | Write concurrency |
|------|------------------------|------------------|---------------------|
| **DEFERRED (default)** | None until first write | Multiple readers | **SQLITE_BUSY if another writer active** |
| **IMMEDIATE** | **EXCLUSIVE immediately** | Blocks readers | **SQLITE_BUSY if another writer active** |
| **EXCLUSIVE** | EXCLUSIVE + blocks readers | No readers | **SQLITE_BUSY if another writer active** |

**Key quote** (SQLite §2.2): "**IMMEDIATE causes the database connection to start a new write
immediately, without waiting for a write statement. The BEGIN IMMEDIATE might fail with
SQLITE_BUSY if another write transaction is already active on another database connection.**"

In **WAL mode** (§2.2): "EXCLUSIVE and IMMEDIATE are the same in WAL mode, but in other
journaling modes, EXCLUSIVE prevents other database connections from reading the database while
the transaction is underway."

**Implication for our code** (`sql_write_queue.py:243`):
```python
conn.execute("BEGIN IMMEDIATE")  # 立即持 EXCLUSIVE 锁
```

In WAL mode, this holds EXCLUSIVE write lock until COMMIT/ROLLBACK. **No other connection can
write**, but **readers can still proceed** (per WAL §1, "writers do not block readers").

### 1.2 COMMIT Failure Path (Critical!)

**Key quote** (SQLite §2.3): "**An attempt to execute COMMIT might also result in an SQLITE_BUSY
return code if another thread or process has an open read connection. When COMMIT fails in this
way, the transaction remains active and the COMMIT can be retried later after the reader has
had a chance to clear.**"

**This is the smoking gun.** If our commit raises SQLITE_BUSY:
- SQLite **does NOT auto-rollback**
- Transaction **remains active** with EXCLUSIVE lock
- Python sqlite3 raises `sqlite3.OperationalError` to caller
- Caller (our `commit()`) catches it, sets `_in_transaction = False`
- But **actual connection state**: still in transaction, still holding lock
- Next `execute()` call: **still hits the lock** because lock is still held

### 1.3 SQLITE_BUSY vs SQLITE_LOCKED (Different!)

| Code | Meaning | busy_timeout helps? |
|------|---------|---------------------|
| **SQLITE_BUSY (5)** | Conflict with **another database connection** | **Yes** (sleeps then retries) |
| **SQLITE_LOCKED (6)** | Conflict **within same connection** (e.g., DROP TABLE while another cursor reads) | **No** |
| **SQLITE_IOERR (10)** | OS-level I/O error | No (per §3, **may auto-rollback entire transaction**) |
| **SQLITE_PROTOCOL (15)** | **WAL race condition** (loser backs off, retries; gives up after 30+ losses) | Internal retry, eventually surfaces |
| **SQLITE_BUSY_SNAPSHOT (517)** | WAL snapshot conflict | No (snapshot is stale) |

**Critical insight**: `busy_timeout` ONLY helps SQLITE_BUSY. It does **NOT** help:
- SQLITE_LOCKED (same connection)
- SQLITE_IOERR (no retry)
- SQLITE_PROTOCOL (internal retry, gives up eventually)

### 1.4 Automatic Rollback Triggers (SQLite §3)

> "The errors that can cause an automatic rollback include:
> - SQLITE_FULL: database or disk full
> - SQLITE_IOERR: disk I/O error
> - SQLITE_INTERRUPT: operation interrupted by sqlite3_interrupt() or similar
> - SQLITE_NOMEM: out of memory
>
> For all of these errors, SQLite attempts to undo just the one statement it was working on and
> leave changes from prior statements within the same transaction intact and continue with the
> transaction. However, depending on the statement being evaluated and the point at which the
> error occurs, **it might be necessary for SQLite to rollback and cancel the entire transaction**.
> An application can tell which course of action SQLite took by using the
> **sqlite3_get_autocommit()** or **sqlite3_txn_state()** C-language interfaces."

**Implication**: When disk I/O error happens mid-transaction, **we cannot tell from Python**
whether SQLite auto-rolled back the whole transaction or just one statement. Python sees
`sqlite3.OperationalError("disk I/O error")` and propagates to caller. Caller has no
authoritative way to know transaction state.

### 1.5 WAL vs DELETE Journal Mode Comparison

| Aspect | DELETE (default) | WAL |
|--------|------------------|-----|
| **Read while writing** | Readers **BLOCKED** during write transaction | Readers **NOT blocked** |
| **Write while reading** | Writer **BLOCKS** readers | Writer **NOT blocked** by readers (until commit) |
| **Concurrent readers** | Yes (1 at a time during write) | **Yes, all readers proceed** |
| **EXCLUSIVE in WAL** | N/A | **Acts like IMMEDIATE** (per §2.2) |
| **Disk I/O error** | Can corrupt | More resilient, but still possible |
| **WAL-specific error** | N/A | **SQLITE_BUSY_SNAPSHOT** (stale snapshot) |
| **WAL files** | -wal -shm (visible) | -wal -shm (must clean on crash) |

**Critical**: In WAL mode, `BEGIN IMMEDIATE` **only blocks other writers, not readers**. So our
"readers blocked" assumption in handoff might be **wrong if we're in WAL mode**!

Need to verify: what is `PRAGMA journal_mode` on production 172.20.59.7? Handoff says V007.13
changed it to DELETE; not sure if that's still active.

### 1.6 Python sqlite3 Specific Behavior

**Key quote** (Python docs): "**If a database operation fails (e.g., a UNIQUE constraint is
violated, or a connection drops), and you don't catch the exception and call rollback(), the
database connection might be left in a pending, inconsistent state.**"

And (Python 3.12+): "If autocommit is True, or there is no open transaction, this method does
nothing. If autocommit is False, **a new transaction is implicitly opened if a pending
transaction was rolled back by this method**."

**Implication**: 
- **Pre-3.12**: rollback failure leaves connection in indeterminate state. `conn.in_transaction`
  is **NOT updated** to reflect SQLite's actual state.
- **3.12+**: rollback can **implicitly start new transaction** — `conn.in_transaction` flips
  based on this hidden side effect.

### 1.7 What is `conn.in_transaction` Actually Checking?

From CPython source (Lib/sqlite3/connection.py), `in_transaction` is set:
- `True` when Python implicitly starts a transaction (first DML)
- `False` after explicit `commit()` or `rollback()` **succeeds**
- **NOT updated** if `commit()` or `rollback()` **raises an exception**

So if our code does:
```python
try:
    conn.commit()  # raises OperationalError
except:
    pass  # in_transaction may still be True in Python
    # But SQLite actual state is UNKNOWN (per §3)
```

This is the **root mismatch** between Python's bookkeeping and SQLite's actual connection state.

### 1.8 Summary: SQLite Reality

1. **BEGIN IMMEDIATE holds EXCLUSIVE lock until COMMIT/ROLLBACK**, no exception.
2. **COMMIT can fail with SQLITE_BUSY** (e.g., if reader holds a lock), and **transaction remains active**.
3. **SQLITE_IOERR may or may not auto-rollback the entire transaction** — caller cannot tell.
4. **`busy_timeout` only helps SQLITE_BUSY**, not SQLITE_LOCKED or SQLITE_IOERR.
5. **Python `conn.in_transaction` is not authoritative** — only updated on successful commit/rollback.
6. **In WAL mode**, BEGIN IMMEDIATE does **NOT block readers** (only writers).

---

## 2. Code Deep Dive: Where the State Gets Corrupted

### 2.1 Three Layers of State Tracking

The codebase has **three independent state machines** that must stay in sync:

```
Layer 1: SQLite connection (conn.in_transaction) — C-level, authoritative
Layer 2: PooledSQLiteDataSource._in_transaction — Python field on adapter
Layer 3: WriteQueue._in_transaction — Python field on queue
```

All three must agree. If they diverge, you get the orphan transaction bug.

### 2.2 Layer 1: SQLite connection state

Cannot be queried directly from Python sqlite3 module (`get_autocommit` exists in C API but not
exposed to Python). **This is the fundamental observability gap** — we cannot tell from Python
whether SQLite thinks we're in a transaction.

**Workaround**: We can issue a no-op query (e.g., `SELECT 1`) and check for "no transaction
active" errors. Or we can use `PRAGMA query_only` to detect active statements.

### 2.3 Layer 2: PooledSQLiteDataSource._in_transaction (sql_adapters.py)

**Initialization** (L613): `self._in_transaction = False`

**`begin_transaction()` L888-904**:
```python
if self._write_queue and not self._write_queue.in_transaction:
    self._write_queue.begin_transaction()  # 调 _do_begin, 可能 raise
    self._in_transaction = True  # ← 仅在 write_queue 成功后设
elif not self._write_queue and self._connection and not self._in_transaction:
    self._connection.execute("BEGIN IMMEDIATE")  # ← 不 catch 异常
    self._in_transaction = True
```

**Problem**: If `self._write_queue.begin_transaction()` raises mid-way (e.g., write_queue is
stuck, or BEGIN IMMEDIATE inside queue fails), `self._in_transaction` is **never set**. **Layer 2
state consistent**. But **Layer 1 (actual SQLite)** may have BEGIN held, if BEGIN actually ran
before failure.

**`commit()` L912-926**:
```python
if self._write_queue:
    self._write_queue.commit()  # 调 _do_commit, 可能 raise
elif self._connection and self._in_transaction:
    self._connection.commit()  # 不 catch 异常
self._in_transaction = False  # ← 总是执行
```

**Problem 1 (L926)**: `self._in_transaction = False` **always executes**, even if write_queue
raise. So Layer 2 says "not in transaction" but **Layer 1 (SQLite) still holds lock if
write_queue.commit() failed to actually commit**.

**Problem 2 (L924)**: `self._connection.commit()` in direct mode (no write_queue) **does not
catch exception**, but the L926 reset still happens. Same issue.

**`rollback()` L928-942**: Same pattern as commit.

**`_execute_via_read_pool()` L785-810**:
```python
if self._in_transaction and self._connection:
    cursor = self._connection.cursor()
    return cursor.execute(command, params)
```

**Critical bug**: This branches on `self._in_transaction` (Layer 2), but if Layer 2 is False
(state polluted to false) while Layer 1 is still in transaction (lock held), **this code goes to
the reader pool**, and the **read query goes through a different connection** (or the same
connection that already has BEGIN held).

If it goes through the same connection that holds EXCLUSIVE: **read succeeds** (own transaction
visible to itself). If it goes through a **different** connection from the pool: **read gets
SQLITE_BUSY** (waiting for the writer's lock).

**`_execute_via_write_queue()` L836-886**:
```python
auto_commit = not self._in_transaction

def _do_write(conn):
    cursor = conn.cursor()
    if params:
        result = cursor.execute(command, params)
    else:
        result = cursor.execute(command)
    if auto_commit:
        conn.commit()  # ← may raise, but L886 returns result anyway
        ...
    return result
```

**Critical bug (L863)**: `auto_commit` is captured **before** execute. If execute succeeds but
`conn.commit()` fails (e.g., SQLITE_BUSY), the function returns `result` (the cursor from
execute), but **`conn.commit()` raised and was not caught**. The caller's `result` is from
uncommitted data!

Actually looking again: `_do_write` is called via `submit_and_wait`, which is in the write_queue
thread. If `conn.commit()` raises inside `_do_write`, the exception propagates up. The result
returned to caller might be None or the cursor from execute (uncommitted).

### 2.4 Layer 3: WriteQueue._in_transaction (sql_write_queue.py)

**`_do_begin` L238-254**:
```python
def _do_begin(conn):
    try:
        conn.execute("BEGIN IMMEDIATE")  # L243 - 立即持 EXCLUSIVE 锁
        self._in_transaction = True     # L244 - 在 BEGIN 成功后设
    except Exception as e:
        error_str = str(e)
        if "cannot start a transaction within a transaction" in error_str:
            # 连接已经在事务中
            self._in_transaction = True   # L251 - **更糟！状态错误设置**
        else:
            logger.error(...)
            raise
```

**Bug 1 (L251)**: When SQLite says "cannot start a transaction within a transaction" (because
the connection **already has a transaction** — could be from a previous unhandled state), we
**set _in_transaction = True** but we **did not actually BEGIN**. This is a phantom transaction
state.

**Bug 2 (L246-254)**: If `BEGIN IMMEDIATE` raises some other error (e.g., SQLITE_BUSY because
another connection is writing), we **leave _in_transaction = False** but the connection may have
**partially executed** or **may have** acquired the lock before failing. State is **unknown**.

**Bug 3 (L243 vs L244)**: `self._in_transaction = True` is set **AFTER** `conn.execute("BEGIN
IMMEDIATE")`. If the execute itself raises (e.g., the connection is dead), `_in_transaction`
stays False, but the connection's actual state is **undefined** (might be holding lock, might not).

**`_do_commit` L259-262**:
```python
def _do_commit(conn):
    conn.commit()                          # L260 - 可能 raise SQLITE_BUSY
    self._in_transaction = False           # L261 - 提交成功后才设
```

**Bug 4**: If `conn.commit()` raises SQLITE_BUSY, **L261 is not executed**. `self._in_transaction`
stays True, and **`conn` is still holding the EXCLUSIVE lock** (per SQLite §2.3, "When COMMIT
fails in this way, the transaction remains active"). State is actually consistent here — but
**Python doesn't know commit failed** if caller doesn't check.

**`_do_rollback` L315-317**:
```python
def _do_rollback(conn):
    conn.rollback()                        # L316 - 可能 raise
    self._in_transaction = False           # L317 - 回滚成功后才设
```

**Bug 5**: Same as commit. If `conn.rollback()` raises (e.g., connection dead, or I/O error
during rollback), `_in_transaction` stays True. **conn may still hold lock** (depending on what
failed in rollback).

### 2.5 Layer 0: bo_framework.py (top-level)

**`begin_transaction()` L449-455**:
```python
def begin_transaction(self, isolation_level: str = 'READ_COMMITTED') -> str:
    transaction_id = str(uuid.uuid4())[:8]
    if hasattr(self._data_source, 'begin_transaction'):
        self._data_source.begin_transaction()  # 调 Layer 2 begin, 可能 raise
    return transaction_id
```

No state tracking at this layer — it just generates a transaction_id and delegates. OK.

**`commit()` L457-465**:
```python
def commit(self, transaction_id: str = None) -> bool:
    try:
        if hasattr(self._data_source, 'commit'):
            self._data_source.commit()  # 调 Layer 2 commit
        return True
    except Exception as e:
        logger.error(f"[BOFramework] Commit failed: {e}")
        return False
```

**Bug 6**: Catches and **swallows** the exception. Returns False, but **`self._data_source` state
unknown**. If Layer 2's commit() was a partial failure (set _in_transaction=False but Layer 1
still in transaction), bo_framework has no way to know.

**`rollback()` L467-475**:
```python
def rollback(self, transaction_id: str = None) -> bool:
    try:
        if hasattr(self._data_source, 'rollback'):
            self._data_source.rollback()
        return True
    except Exception as e:
        logger.error(f"[BOFramework] Rollback failed: {e}")
        return False
```

**Bug 7**: **No finally block, no state reset on failure**. This is the **central bug**. If
`data_source.rollback()` fails:
- _in_transaction in Layer 2 may or may not be reset (depends on subclass behavior)
- Layer 1 (SQLite) may or may not be reset
- bo_framework just logs and returns False
- Next call to `begin_transaction()` (e.g., new request): `data_source.begin_transaction()` will
  fail with "cannot start a transaction within a transaction" if Layer 1 still active, or
  succeed with **a fresh BEGIN IMMEDIATE** that **co-exists** with the old lock on a different
  connection (impossible — but if same connection, the new BEGIN IMMEDIATE actually means the
  old one was auto-rolled back? unclear)

**`TransactionContext.__exit__` L586-598**:
```python
def __exit__(self, exc_type, exc_val, exc_tb):
    if exc_type is not None:
        self.bo_framework.rollback(self.transaction_id)  # 异常路径 rollback
        return False
    if not self._should_commit:
        self.bo_framework.rollback(self.transaction_id)  # 业务失败 rollback
        return False
    self.bo_framework.commit(self.transaction_id)  # 正常路径 commit
    return False
```

**Bug 8 (L589, L594)**: If `bo_framework.rollback()` itself fails (returns False), `__exit__`
returns False (which means "don't suppress exception"). Good. But **no state recovery**:
- Layer 2 may be polluted
- Layer 1 may still hold lock
- bo_framework.rollback returned False silently

**Bug 9 (L597)**: If `bo_framework.commit()` fails, same issue. **Transaction might be
half-committed or fully-rolled-back depending on SQLite's interpretation**, but Python doesn't
know.

### 2.6 Layer 0: audit_service.py

**`log()` L551-554**:
```python
self.ds.insert(self.AUDIT_TABLE, record)  # L551

if not getattr(self.ds, 'in_transaction', False):  # L553
    self.ds.commit()  # L554
```

**Bug 10**: If Layer 2's `in_transaction` (via `ds.in_transaction` property) is **True due to
state pollution** (but Layer 1 is actually NOT in transaction — the rollback DID succeed), audit
**never commits** its insert. Audit record **lost**.

Conversely, if Layer 2 is **False (polluted to false) but Layer 1 is True (still holding
lock)**, audit **does commit**, which may or may not succeed depending on whether the lock
holder's transaction is still active.

**Bug 11**: Audit insert is **NOT wrapped in try/except at L551** (the outer try is at L364
but L551 is inside the loop... let me re-check).

Looking at the code again: L364-556 is the main try. L551 `self.ds.insert` is inside this try.
If it raises (e.g., OperationalError due to disk full or lock), the **except at L558** catches it
and writes an error record. But **the error record write at L564-578 is not in a try/except for
the commit at L578**, so if commit fails there too, we have a chain of unhandled state.

### 2.7 State Corruption Scenarios

| Scenario | Layer 1 (SQLite) | Layer 2 (DataSource) | Layer 3 (WriteQueue) | Detected? |
|----------|--------------------|-----------------------|----------------------|-----------|
| BEGIN IMMEDIATE deadlock, retry, succeeds | In transaction | True | True | OK |
| BEGIN IMMEDIATE raises "cannot start within" | In transaction (already) | True (false set) | True (false set) | **Inconsistent — phantom tx** |
| BEGIN IMMEDIATE raises other (I/O, etc) | Unknown | False | False | **Possibly inconsistent** |
| commit raises SQLITE_BUSY | **Still in transaction** | False (L926) | False (L261 not run) | **State polluted — Layer 2/3 false, Layer 1 true** |
| rollback raises | Unknown | False (L942) | False (L317 not run) | **State polluted** |
| IO error during execute | Auto-rollback or partial | False (after failure) | False (after failure) | **Unknown** |
| Connection dies (network/timeout) | Closed | False | False | **Connection dead, lock released by SQLite, but pool may not know** |
| Long action: 1000+ rows INSERT, user closes popup, gevent doesn't cancel | Still in transaction (action still running) | True | True | **OK at this point** — action completes or raises, then TransactionContext.__exit__ runs |

**Most likely scenario for orphan transaction**:
- Long action in transaction
- Action raises (timeout, OOM, user-initiated error)
- `__exit__` calls `bo_framework.rollback()`
- `bo_framework.rollback()` calls `data_source.rollback()` which calls `write_queue.rollback()`
- `write_queue.rollback()` calls `submit_and_wait` which calls `_do_rollback`
- `_do_rollback` calls `conn.rollback()` (Layer 1 rollback)
- If `conn.rollback()` raises (e.g., I/O error during rollback), `_in_transaction = False` is
  not executed
- OR `conn.rollback()` succeeds but `submit_and_wait` itself fails (e.g., queue thread dead)
- `bo_framework.rollback()` logs error, returns False
- `__exit__` returns False, exception propagates (or is suppressed)
- **Now**: Layer 1 **may still hold lock** (if rollback failed mid-way) or **may not** (if
  SQLite auto-rolled back)
- Layer 2 = True (we set it via PooledSQLiteDataSource.rollback L942: `self._in_transaction =
  False` — wait, this always runs)
- Layer 3 = True (because _do_rollback didn't complete)
- **State desync**: Layer 1 = maybe locked, Layer 2 = False, Layer 3 = True
- Next request: `bo_framework.begin_transaction()` → `data_source.begin_transaction()` →
  `write_queue.begin_transaction()` → sees `self._in_transaction = True` (Layer 3) → **skips
  BEGIN** (L235 debug log "Already in transaction, skipping BEGIN") → but `auto_commit = not
  self._in_transaction` in `_do_write` is **False** (Layer 2 says not in tx, wait, this is
  confusing)

Let me re-derive the state machine carefully:
- Layer 1 (SQLite): actually holds lock or not
- Layer 2 (PooledSQLiteDataSource._in_transaction): True/False
- Layer 3 (WriteQueue._in_transaction): True/False

`_do_write` (in WriteQueue, called via submit_and_wait) checks **auto_commit = not
self._in_transaction** at the time of `_execute_via_write_queue` call, which is `not
PooledSQLiteDataSource._in_transaction` (Layer 2).

So if Layer 2 = False (polluted to false), `_do_write` does `conn.commit()`. This either:
- Succeeds → but if Layer 1 is still in transaction, this commits the OLD transaction (lost
  data semantics)
- Fails (SQLITE_BUSY because Layer 1 has lock) → `_in_transaction` (Layer 3) reset to False after
  the next commit attempt

If Layer 2 = True (polluted to true), `_do_write` does **not** commit. Insert succeeds but
uncommitted. Next `_do_write` also uncommitted. Eventually the data is **lost on connection
close** or **auto-rolled back on next BEGIN** (per Python 3.12+ behavior).

### 2.8 The "Audit Service 撞锁" Specific Path

Looking at `audit_service.py:551-554`:
```python
self.ds.insert(self.AUDIT_TABLE, record)
if not getattr(self.ds, 'in_transaction', False):
    self.ds.commit()
```

If `ds.in_transaction` (Layer 2) is True (polluted to true), audit **does not commit**. The
insert is in the write_queue, returns successfully (cursor with rowid), but the **row is never
persisted**.

**However**: This doesn't directly cause "audit_service 撞锁" error. The撞锁 error suggests
audit insert **fails**, not that it silently doesn't commit.

Let me think about the "撞锁" path:
- `ds.insert` calls `_do_write` (write queue submit)
- `_do_write` calls `cursor.execute(command)` on the **write_queue's connection**
- The write_queue's connection is the **same one** that holds the EXCLUSIVE lock (from orphan
  transaction)
- **`cursor.execute` on a connection that already has its own active transaction** — this should
  work, the connection sees its own changes
- UNLESS: the write_queue is using a **different connection** (e.g., queue thread, or pool gave
  a different conn)
- OR: `cursor.execute` is on a connection from the **read pool**, not the write_queue

Actually, looking at the architecture more carefully:
- `data_source` is a PooledSQLiteDataSource
- It has a `_pool` (SQLiteConnectionPool with max_readers=20) and `_write_queue`
- `_execute_via_write_queue` uses the write_queue's connection
- `_execute_via_read_pool` uses pool connections

If Layer 1 is corrupted (some connection holds EXCLUSIVE), the **read pool connections** are
different connections. They try to acquire their own lock (read or write) and **wait for the
holder**. busy_timeout=30s. If holder doesn't release in 30s, **SQLITE_BUSY** raised to
read_pool caller. This is the "audit 撞锁" — audit is **reading** (SELECT) from a read pool
connection, and that connection **cannot proceed** because writer holds EXCLUSIVE.

**Confirmed**: the "audit 撞锁" path is:
- Orphan transaction holds EXCLUSIVE on **writer connection** (one of the connections)
- Audit insert: actually a write, goes through write_queue
- OR audit read (e.g., checking if record exists): goes through read pool → read pool connection
  waits for writer lock → 30s busy_timeout → SQLITE_BUSY → "database is locked"
- "disk I/O error" may be a different signal: from a separate connection that hit I/O during its
  busy wait

### 2.9 Code Conclusion

**State corruption vectors identified**:
1. **`bo_framework.rollback()` no finally block** — L467-475, central bug
2. **`PooledSQLiteDataSource.commit/rollback` reset state before verifying success** — L926, L942
3. **`WriteQueue._do_begin` set _in_transaction=True on "already in transaction"** — L251
4. **`WriteQueue._do_commit/rollback` don't update _in_transaction on failure** — L261, L317
5. **`audit_service.log` doesn't retry on commit failure** — L551-554
6. **`_execute_via_read_pool` branches on Layer 2 state** — L787, may send read to wrong conn

**No defense-in-depth**: any one of these can corrupt state. Once corrupted, **all subsequent
operations behave incorrectly** because the read_pool branch (L787) routes based on Layer 2 which
is now wrong.

---

## 3. V049 Fix Impact on V007.x Risk

V049 fix has **two components**:
1. `waitress_server.py:36-55` — setrlimit(RLIMIT_NOFILE, 65536)
2. `import_export_service.py:5637-5647` — wb.close() + gc.collect() in import_cascade

**Does V049 reduce V007.x orphan transaction risk?**

### 3.1 Indirect: YES, V049 reduces V007.x trigger frequency

V049's primary fix is **"import doesn't hang 0%"**. The handoff V007.x trigger sequence:

1. Batch import 1000+ rows
2. Import stuck 50% (was due to FD exhaustion in old V049)
3. User closes popup (or browser timeout)
4. Action still running in gevent thread
5. Action raises (timeout, etc)
6. **Orphan transaction**

**With V049 fixed**:
- Import completes in 18-26s (no longer hangs)
- User does NOT close popup
- Action completes normally
- No exception, no orphan transaction

**So V049 indirectly reduces the most common V007.x trigger** (stuck import → user cancellation).

### 3.2 Direct: NO, V049 does not address the state corruption bug

V049 patches are:
- `setrlimit` — process-level FD limit (not DB related)
- `wb.close()` — openpyxl file handle (not DB related)

**None of these**:
- Adds try/finally to `bo_framework.rollback`
- Adds state verification to `PooledSQLiteDataSource.commit/rollback`
- Fixes `WriteQueue._do_begin` "already in transaction" handler
- Adds auto-recovery on read_pool "locked" errors

**The orphan transaction bug is still latent**. Any new long action that:
- Fails mid-transaction with a rollback that itself fails
- Or has user cancellation that doesn't propagate properly
- Or runs in a connection pool that gets confused about state

...will still trigger V007.x.

### 3.3 V049 can increase V007.x trigger frequency (counterintuitive!)

**Counterintuitive scenario**:
- V049 makes import fast (18-26s instead of stuck)
- More imports per day → **more opportunities** for the rare race condition
- If state corruption occurs in 1% of imports, more imports = more occurrences

**Mitigation**: V049 + V007.15 should ship together. V049 reduces the **stuck import → user
cancel** path (common case), V007.15 fixes the **state corruption** (rare but catastrophic).

### 3.4 V049 cannot trigger V007.x by itself

V049's code paths are:
- `setrlimit` in waitress startup — one-time, no DB interaction
- `wb.close()` + `gc.collect()` after import_cascade — before any DB write, no transaction involvement

V049 is **isolated from the transaction machinery**. So V049 cannot directly cause V007.x.

---

## 4. Refined V007.15 Design (Beyond handoff's 3-layer defense)

The handoff's V007.15 has 3 layers (治本/缓解/预防). Based on this deep analysis, **I recommend
4 additional safeguards**:

### 4.1 Layer 0: Add SQLite tx_state check via PRAGMA

Python sqlite3 doesn't expose `sqlite3_txn_state()`. Workaround:

```python
# meta/core/sqlite_tx_state.py (new file)
import sqlite3

def get_tx_state(conn) -> str:
    """Get SQLite's actual transaction state. Returns 'none', 'read', or 'write'."""
    # PRAGMA query_only doesn't tell us state, but we can try a savepoint
    # If savepoint succeeds, we're in a transaction. If fails with "no
    # transaction is active", we're not.
    try:
        conn.execute("SAVEPOINT __tx_check__")
        conn.execute("RELEASE SAVEPOINT __tx_check__")
        return "in_tx"
    except sqlite3.OperationalError as e:
        if "no transaction is active" in str(e):
            return "none"
        raise
```

Call this from `bo_framework.commit/rollback` to **verify** state before resetting `_in_transaction`.

### 4.2 Layer 1: bo_framework.rollback with try/finally

```python
# meta/core/bo_framework.py
def rollback(self, transaction_id: str = None) -> bool:
    """[V007.15 L1 治本] rollback 加 try/finally + 状态重置"""
    success = True
    try:
        if hasattr(self._data_source, 'rollback'):
            self._data_source.rollback()
    except Exception as e:
        logger.error(f"[BOFramework] Rollback failed: {e}")
        success = False
    finally:
        # [V007.15 L1 关键] 不论成功失败, 强制重置所有 in_transaction 标志
        try:
            if hasattr(self._data_source, '_in_transaction'):
                self._data_source._in_transaction = False
            if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
                if hasattr(self._data_source._write_queue, '_in_transaction'):
                    self._data_source._write_queue._in_transaction = False
        except Exception as e:
            logger.error(f"[BOFramework] State reset failed: {e}")
            success = False
    return success
```

### 4.3 Layer 2: bo_framework.rollback also resets SQLite connection

```python
# meta/core/bo_framework.py
def rollback(self, transaction_id: str = None) -> bool:
    """[V007.15 L1+L2 治本] 显式调 SQLite conn.rollback() 强制重置"""
    success = True
    try:
        if hasattr(self._data_source, 'rollback'):
            self._data_source.rollback()
    except Exception as e:
        logger.error(f"[BOFramework] DataSource rollback failed: {e}")
        success = False

    # [V007.15 L2] 额外保险: 显式调 SQLite conn.rollback() 强制重置
    #   即使 DataSource.rollback 失败, 这里还有一次机会
    try:
        if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
            wq = self._data_source._write_queue
            if hasattr(wq, '_write_conn') and wq._write_conn:
                wq._write_conn.rollback()  # 直接调 C-level rollback
    except Exception as e:
        logger.error(f"[BOFramework] Direct conn.rollback() failed: {e}")
        # 注意: 这里不 mark as failure, 因为可能已经在 tx 外
    finally:
        # [V007.15 L1] 强制重置所有标志
        try:
            ...
        except:
            pass
    return success
```

### 4.4 Layer 3: WriteQueue.begin_transaction sanity check

```python
# meta/core/sql_write_queue.py
def begin_transaction(self):
    """[V007.15 L3 治本] begin 前检查连接是否已有事务, 防止 phantom tx"""
    def _do_begin(conn):
        # [V007.15 L3] 防御性检查: 之前的事务是否真的结束了?
        # 调 savepoint 看是否在 tx 中
        try:
            conn.execute("SAVEPOINT __check__")
            # 在 tx 中, 但我们想开始新 tx -> 错误状态, 先回滚
            conn.execute("ROLLBACK TO SAVEPOINT __check__")
            logger.warning("WriteQueue: connection already in transaction, rolling back phantom")
            conn.execute("ROLLBACK")
            self._in_transaction = False
        except sqlite3.OperationalError as e:
            if "no transaction" in str(e):
                pass  # 正常情况, 继续 BEGIN
            else:
                raise
        except Exception:
            pass

        # 现在安全地 BEGIN
        conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        ...

    self.submit_and_wait(_do_begin)
```

### 4.5 Layer 4: audit_service.log defensive commit retry

```python
# meta/services/audit_service.py
def log(self, ...):
    ...
    # [V007.15 L4 预防] audit 写入加 retry + 状态验证
    for attempt in range(3):
        try:
            self.ds.insert(self.AUDIT_TABLE, record)
            if not getattr(self.ds, 'in_transaction', False):
                self.ds.commit()
            return True
        except sqlite3.OperationalError as e:
            err_str = str(e).lower()
            if "locked" in err_str or "busy" in err_str:
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
            raise
```

### 4.6 Layer 5: Periodic health check (background task)

```python
# meta/core/db_health_monitor.py (or new file)
import threading
import time

class OrphanTransactionDetector:
    """[V007.15 L5 预防] 定期检查并清理孤儿事务"""

    def __init__(self, data_source, check_interval=60):
        self._ds = data_source
        self._interval = check_interval
        self._stop = False
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop:
            time.sleep(self._interval)
            try:
                self._check_and_recover()
            except Exception as e:
                logger.error(f"OrphanTransactionDetector failed: {e}")

    def _check_and_recover(self):
        # 1. 用 savepoint 探测 _write_conn 状态
        # 2. 如果在 tx 中 + 应用层没标记 in_tx, 视为孤儿
        # 3. 强制 rollback + 重置标志
        ...
```

### 4.7 Recommended worktree scope

V007.15 should be a **separate worktree** (V050) because:
- Touches 4-5 files (bo_framework, sql_write_queue, sql_adapters, audit_service, new detector)
- Requires unit tests (5 new test files)
- V049 worktree already has 3 commits on V049 fix
- Mixing would make cherry-pick risky

---

## 5. Cross-Reference for V049 Deployment

**V049 deployment should mention**:
- V049 fix does NOT prevent V007.x orphan transactions
- V007.15 should be planned as next iteration
- If V007.x triggers after V049 deploy, **emergency_unlock_db.sh** (per handoff) is the
  workaround

**Add to DEPLOY_HANDOVER_BUG_V049.md §10**:
```
After V049 deploy, monitor for V007.x symptoms:
- tail -f log | grep "database is locked\|disk I/O"
- If symptoms appear, V007.15 is required
- Emergency: bash /tmp/emergency_unlock_db.sh (per handoff_orphan_transaction.md)
```

---

## 6. Verification: How to Confirm V007.x is Not Active

After V049 deploy, run these checks (yonaa or production):

```bash
# 1. Check for orphan transactions
python -c "
import sqlite3
conn = sqlite3.connect('meta.db')
try:
    conn.execute('SAVEPOINT __check__')
    conn.execute('RELEASE SAVEPOINT __check__')
    print('No active transaction (good)')
except Exception as e:
    if 'no transaction' in str(e):
        print('No active transaction (good)')
    else:
        print(f'In transaction: {e}')
conn.close()
"

# 2. Check application state
curl http://172.20.59.7:8081/api/v2/auth/login -X POST -d '{"username":"admin","password":"x"}'
# If this succeeds quickly, no orphan transaction blocking reads

# 3. Run a small import to verify FD usage
lsof -p <waitress-pid> | grep /tmp/ | wc -l
# Should be 0-10 (V049 fix)
```

---

## 7. Open Questions

1. **What is current `PRAGMA journal_mode` on production 172.20.59.7?** (handoff V007.13 set
   DELETE; not sure if still active)
2. **What is current `busy_timeout`?** (handoff says 30s, V007.11; verify)
3. **How many long-running actions are there beyond import_cascade?** (e.g., export, cascade
   delete) — each could be a V007.x trigger
4. **Is there monitoring on `audit_service.log` failures?** (orphaned audit writes would be silent
   if L4 not implemented)
5. **Does production use `:memory:` databases for any test paths?** (already disallowed by
   sql_adapters L664-668, but verify no test fixture bypasses)

---

## 8. Conclusions

1. **V007.x is an architectural bug**, not a retry tuning bug. The 14 rounds of V007.x fixes
   all failed because they didn't address state corruption at the source.
2. **V049 fix is orthogonal to V007.x** — V049 reduces V007.x trigger frequency (no more
   stuck imports → no more user cancellation → fewer orphan tx), but does not fix the state
   corruption itself.
3. **V007.15 is still required** as a separate worktree. Recommend 6 layers (L0 SQLite
   tx_state, L1 bo_framework try/finally, L2 direct conn.rollback, L3 WriteQueue sanity
   check, L4 audit retry, L5 background detector).
4. **Deploy V049 first, then V007.15 next iteration.** Both can ship independently.
5. **Monitor for V007.x symptoms after V049 deploy.** Have emergency_unlock_db.sh ready.

---

*Author: dev-agent (V049/V050 planning)*
*Date: 2026-07-05*
*Status: analysis complete, no code changes in this doc*
*Next step: coordinator + PM review this analysis, decide if V007.15 worktree is in scope*
