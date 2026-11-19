"""POC-5 (collab round 1, consultant): is "O_EXCL create; if the holder is stale,
rename it aside and retry" safe when several tabs replace the SAME stale claim?

Three algorithms race over one member whose claim file is pre-seeded stale:
  naive   -- the candidate design's B3-a as written
  verify  -- rename aside, then check the moved file is the one judged stale;
             if not, put it back (os.rename fails if a new claim exists)
  oslock  -- the whole judge/remove/create step under an OS byte-range lock
             (msvcrt.locking / fcntl.flock) that the OS drops when a process dies

Safe: temp folder only. Usage: python poc5_stale_claim_race.py [workers] [trials]
"""
import json, os, sys, tempfile, time, subprocess

def stale(rec):
    return rec.get("holder") == "DEAD"

def excl_create(path, me):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w") as f:
        json.dump({"holder": me}, f)

def read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, PermissionError, ValueError):
        return None

def claim_naive(d, me):
    path = os.path.join(d, "member.json")
    for _ in range(50):
        try:
            excl_create(path, me); return True
        except FileExistsError:
            pass
        except PermissionError:
            continue
        rec = read(path)
        if rec is None:
            continue
        if not stale(rec):
            return False
        try:
            os.replace(path, path + ".stale.%s" % me)
        except (FileNotFoundError, PermissionError):
            pass
    return False

def claim_verify(d, me):
    path = os.path.join(d, "member.json")
    for i in range(50):
        try:
            excl_create(path, me); return True
        except FileExistsError:
            pass
        except PermissionError:
            continue
        rec = read(path)
        if rec is None:
            continue
        if not stale(rec):
            return False
        aside = path + ".stale.%s.%d" % (me, i)
        try:
            os.replace(path, aside)
        except (FileNotFoundError, PermissionError):
            continue
        moved = read(aside)
        if moved is not None and not stale(moved):
            try:
                os.rename(aside, path)      # put the live claim back
            except OSError:
                open(os.path.join(d, "LOST.%s" % me), "w").close()  # a live claim was destroyed
            return False
    return False

def claim_oslock(d, me):
    path = os.path.join(d, "member.json")
    lockp = os.path.join(d, ".lock")
    fd = os.open(lockp, os.O_CREAT | os.O_RDWR)
    try:
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1); break
                except OSError:
                    time.sleep(0.001)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        rec = read(path)
        if rec is not None and not stale(rec):
            return False
        with open(path, "w") as f:
            json.dump({"holder": me}, f)
        return True
    finally:
        os.close(fd)   # closing the handle releases the lock; so does process death

def claim_naive_backoff(d, me):
    """naive, plus a jittered sleep whenever Windows refuses the rename/create
    (another process has the file open) -- the fair version of B3-a."""
    import random
    path = os.path.join(d, "member.json")
    for _ in range(400):
        try:
            excl_create(path, me); return True
        except FileExistsError:
            pass
        except PermissionError:
            time.sleep(random.random() * 0.003); continue
        rec = read(path)
        if rec is None:
            time.sleep(random.random() * 0.003); continue
        if not stale(rec):
            return False
        try:
            os.replace(path, path + ".stale.%s" % me)
        except (FileNotFoundError, PermissionError):
            time.sleep(random.random() * 0.003)
    return False

def deterministic_interleave():
    """No timing involved: the one interleaving that breaks rename-aside."""
    d = tempfile.mkdtemp(prefix="relaunch_poc5_det_")
    path = os.path.join(d, "member.json")
    with open(path, "w") as f: json.dump({"holder": "DEAD"}, f)
    t2_saw = read(path)                               # T2 reads: stale
    os.replace(path, path + ".stale.T1"); excl_create(path, "T1")   # T1 replaces and wins
    assert stale(t2_saw)                              # T2 still acts on its old reading
    os.replace(path, path + ".stale.T2"); excl_create(path, "T2")   # moves T1's LIVE claim aside
    print("deterministic interleave: T1 believes it holds the member; file now says holder=%s; "
          "T1's live claim sits in %s" % (read(path)["holder"], "member.json.stale.T2"))

ALGOS = {"naive": claim_naive, "naive_backoff": claim_naive_backoff, "verify": claim_verify, "oslock": claim_oslock}

def worker(root, algo, trials, t0, step):
    me = str(os.getpid())
    fn = ALGOS[algo]
    for i in range(trials):
        target = t0 + i * step
        while time.time() < target:
            pass
        d = os.path.join(root, algo, "t%04d" % i)
        if fn(d, me):
            open(os.path.join(d, "WIN.%s" % me), "w").close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]))
        sys.exit(0)
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    trials = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    deterministic_interleave()
    root = tempfile.mkdtemp(prefix="relaunch_poc5_")
    print("root:", root, "workers", workers, "trials", trials)
    for algo in ALGOS:
        for i in range(trials):
            d = os.path.join(root, algo, "t%04d" % i); os.makedirs(d)
            with open(os.path.join(d, "member.json"), "w") as f:
                json.dump({"holder": "DEAD"}, f)
        t0 = time.time() + 2.0
        ps = [subprocess.Popen([sys.executable, __file__, "--worker", root, algo, str(trials), repr(t0), "0.02"])
              for _ in range(workers)]
        for p in ps:
            p.wait()
        zero = one = multi = lost = mismatch = 0
        for i in range(trials):
            d = os.path.join(root, algo, "t%04d" % i)
            names = os.listdir(d)
            wins = [n[4:] for n in names if n.startswith("WIN.")]
            lost += sum(1 for n in names if n.startswith("LOST."))
            rec = read(os.path.join(d, "member.json")) or {}
            if len(wins) == 0: zero += 1
            elif len(wins) == 1:
                one += 1
                if rec.get("holder") != wins[0]: mismatch += 1
            else: multi += 1
        print("%-7s exactly-one=%d  DOUBLE-CLAIM=%d  nobody=%d  winner!=file=%d  live-claim-destroyed=%d"
              % (algo, one, multi, zero, mismatch, lost))
