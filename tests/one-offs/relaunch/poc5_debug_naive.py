"""Debug aid for poc5: log what each racing worker saw in the naive algorithm."""
import json, os, sys, tempfile, time, subprocess
import poc5_stale_claim_race as p

def claim(d, me, log):
    path = os.path.join(d, "member.json")
    for it in range(50):
        try:
            p.excl_create(path, me); log.append("create-ok@%d" % it); return True
        except FileExistsError:
            log.append("exists")
        except PermissionError as e:
            log.append("create-perm"); continue
        rec = p.read(path)
        if rec is None:
            log.append("read-none"); continue
        if not p.stale(rec):
            log.append("live:%s" % rec.get("holder")); return False
        try:
            os.replace(path, path + ".stale.%s" % me); log.append("moved")
        except FileNotFoundError:
            log.append("move-nf")
        except PermissionError:
            log.append("move-perm")
    log.append("EXHAUSTED"); return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--w":
        d, t0 = sys.argv[2], float(sys.argv[3])
        while time.time() < t0: pass
        log = []; r = claim(d, str(os.getpid()), log)
        open(os.path.join(d, "LOG.%s" % os.getpid()), "w").write("%s %s" % (r, " ".join(log)))
    else:
        shown = 0
        for trial in range(40):
            d = tempfile.mkdtemp(prefix="relaunch_poc5dbg_")
            json.dump({"holder": "DEAD"}, open(os.path.join(d, "member.json"), "w"))
            t0 = time.time() + 1.0
            ps = [subprocess.Popen([sys.executable, __file__, "--w", d, repr(t0)]) for _ in range(8)]
            [q.wait() for q in ps]
            logs = [open(os.path.join(d, n)).read() for n in os.listdir(d) if n.startswith("LOG.")]
            wins = sum(1 for l in logs if l.startswith("True"))
            if wins != 1 and shown < 3:
                shown += 1
                print("trial", trial, "winners", wins, os.listdir(d)[:4])
                for l in logs: print("   ", l[:200])
        print("done")
