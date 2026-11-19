"""POC-6 (collab round 2, consultant): msvcrt.locking as the claim lock.
 a) does locking byte 0 of an EMPTY lock file work?
 b) holder killed with `taskkill /f` while holding: how long until another
    process acquires?
 c) what does a second locker see while the holder is alive (non-blocking)?
 d) does opening the lock file read-only (no O_CREAT) leave the folder untouched
    when the file is absent?
Safe: temp folder only; kills only the child python this script started.
"""
import os, subprocess, sys, tempfile, time

def lock(fd):
    import msvcrt
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

if len(sys.argv) > 1 and sys.argv[1] == "--hold":
    fd = os.open(sys.argv[2], os.O_CREAT | os.O_RDWR)
    lock(fd)
    open(sys.argv[2] + ".held", "w").close()
    time.sleep(120)
    sys.exit(0)

root = tempfile.mkdtemp(prefix="relaunch_poc6_")
lp = os.path.join(root, ".lock")
print("root:", root)
results = []
for trial in range(5):
    if os.path.exists(lp + ".held"):
        os.remove(lp + ".held")
    p = subprocess.Popen([sys.executable, __file__, "--hold", lp])
    while not os.path.exists(lp + ".held"):
        time.sleep(0.005)
    if trial == 0:
        print("a) lock file size while locked: %d bytes (lock on byte 0 of an empty file: OK)" % os.path.getsize(lp))
        fd = os.open(lp, os.O_RDWR)
        try:
            lock(fd); print("c) second locker ACQUIRED while holder alive  <-- BROKEN")
        except OSError as e:
            print("c) second locker while holder alive: refused (%s: %s)" % (type(e).__name__, e))
        os.close(fd)
    t0 = time.perf_counter()
    subprocess.run(["taskkill", "/f", "/pid", str(p.pid)], capture_output=True)
    t_kill = time.perf_counter() - t0
    fd = os.open(lp, os.O_RDWR)
    tries = 0
    while True:
        tries += 1
        try:
            lock(fd); break
        except OSError:
            time.sleep(0.001)
    dt = time.perf_counter() - t0
    os.close(fd)
    p.wait()
    results.append((t_kill, dt, tries))
    print("b) trial %d: taskkill returned after %.3fs; lock acquired %.3fs after issuing the kill (%d attempts)" % (trial, t_kill, dt, tries))
d2 = os.path.join(root, "empty"); os.mkdir(d2)
try:
    os.open(os.path.join(d2, ".lock"), os.O_RDONLY)
except FileNotFoundError:
    pass
print("d) read-only open of a missing lock file leaves the folder empty:", os.listdir(d2) == [])
# e) LK_LOCK (blocking form) behaviour note
import msvcrt
p = subprocess.Popen([sys.executable, __file__, "--hold", lp + "2"])
while not os.path.exists(lp + "2.held"):
    time.sleep(0.005)
fd = os.open(lp + "2", os.O_RDWR)
t0 = time.perf_counter()
try:
    msvcrt.locking(fd, msvcrt.LK_LOCK, 1); print("e) LK_LOCK acquired?!")
except OSError as e:
    print("e) msvcrt.LK_LOCK against a live holder gave up after %.1fs with %s (it is NOT an indefinite wait)" % (time.perf_counter() - t0, type(e).__name__))
os.close(fd); p.kill(); p.wait()
