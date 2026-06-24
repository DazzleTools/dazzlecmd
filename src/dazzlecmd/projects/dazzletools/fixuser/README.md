# fixuser (alias: fixusr)

Diagnose and repair a broken Windows user profile -- the "you've been signed in
with a temporary profile" / `C:\Users\TEMP` situation that follows running
`takeown` or `icacls /reset` on a live profile.

```
dz fixuser <user|SID>            # diagnose only (read-only) -- the default
dz fixuser <user|SID> --repair   # apply the fix (elevated shell required)
dz fixuser <user|SID> -vv        # verbose: name the broken shape + raw values
```

It is Windows-only and only orchestrates built-in tools (`reg`, `icacls`, and
`safe-icacls`). There is no magic -- the section below is the exact native
sequence, so you can do it by hand or audit what the tool does.

---

## What `dz fixuser localuser --repair` does, in plain `cmd`/`icacls`/`reg`

> Run in an **elevated** PowerShell/cmd. The target account must be **logged off**
> (no open session, no `runas`). `<SID>` below is the account's SID; the worked
> example account `localuser` had SID `S-1-5-21-...-1014`.

### 0. Resolve the SID (PowerShell -- `cmd` has no clean built-in)

```powershell
([System.Security.Principal.NTAccount]"localuser").Translate([System.Security.Principal.SecurityIdentifier]).Value
# -> S-1-5-21-...-1014
```

### 1. Diagnose (read-only)

```bat
:: the ProfileList entry (and any backup of it)
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<SID>"      /v ProfileImagePath
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<SID>"      /v State
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<SID>.bak"  /v ProfileImagePath

:: is the profile in use right now? (if this key EXISTS, stop -- log the user off first)
reg query "HKU\<SID>"

:: does the user still have FullControl on its own hive? (the load-blocker)
icacls "C:\Users\localuser\AppData\Local\Microsoft\Windows\UsrClass.dat"
```

What the tool decides from this:
- the **real profile path** (from the `.bak` key, or the active key, else `C:\Users\localuser`)
- the **broken shape** (see the table below)
- whether the **ACL** is broken (user missing `(F)` on its hive files)
- refuses to continue if **not elevated** or the **hive is loaded**

### 2. Back up first

```bat
mkdir "%USERPROFILE%\.fixuser\backups\<SID>_<timestamp>"
reg export "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList" ^
           "%USERPROFILE%\.fixuser\backups\<SID>_<timestamp>\ProfileList.reg" /y
icacls "C:\Users\localuser" > "%USERPROFILE%\.fixuser\backups\<SID>_<timestamp>\acls-before.txt"
```

### 3. Fix the ACLs -- give the user back FullControl (ADDITIVE)

This is the actual repair for the "temporary profile" cause. The profile won't
load because the user lost write access to its own registry hives. We **add** the
right back -- we do not take ownership, do not reset, do not remove anything.

```bat
:: full tree, the LOOP-SAFE way (plain "icacls /T" can hang -- see note below):
dz safe-icacls "C:\Users\localuser" /grant "*<SID>:(OI)(CI)F" /T /C
```

If you want pure built-ins and just need the account to log in again, the three
load-critical objects are enough (no `/T`, so no junction loop):

```bat
icacls "C:\Users\localuser"                                              /grant "*<SID>:(OI)(CI)F"
icacls "C:\Users\localuser\NTUSER.DAT"                                   /grant "*<SID>:(F)"
icacls "C:\Users\localuser\AppData\Local\Microsoft\Windows\UsrClass.dat" /grant "*<SID>:(F)"
```

### 4. Fix the ProfileList registry key (depends on the shape)

`reg` cannot *rename* a key, so renames use PowerShell `Rename-Item` (or regedit
GUI: right-click the key -> Rename). Setting values uses `reg add`.

| Shape (what `-vv` reports) | Registry fix |
|---|---|
| **BAK-ONLY** (only `<SID>.bak` exists) | rename `<SID>.bak` -> `<SID>`, then State/RefCount = 0 |
| **TEMP-ACTIVE + BAK** (active `<SID>` -> `\Users\TEMP`, plus `<SID>.bak`) | rename `<SID>` -> `<SID>.temp` (park it), rename `<SID>.bak` -> `<SID>`, then State/RefCount = 0 |
| **TEMP-ACTIVE, NO BAK** (single `<SID>` -> `\Users\TEMP`) | re-point `ProfileImagePath` back to the real path, then State = 0 |
| **STATE-FLAGGED** (right path, `State != 0`) | State = 0 |

```powershell
# rename (PowerShell registry provider):
Rename-Item "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<SID>.bak" -NewName "<SID>"
```

```bat
:: clear the flags so Windows loads the profile normally:
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<SID>" /v State    /t REG_DWORD /d 0 /f
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<SID>" /v RefCount /t REG_DWORD /d 0 /f

:: (TEMP-ACTIVE, NO BAK only) put the real path back:
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<SID>" /v ProfileImagePath /t REG_EXPAND_SZ /d "C:\Users\localuser" /f
```

### 5. Verify

Log the account off and on (or reboot), then in its shell:

```bat
echo %USERPROFILE%      ::  -> C:\Users\localuser   (NOT C:\Users\TEMP)
```

---

## Why NOT `takeown`?

`takeown` is what *causes* this problem. It only assigns **ownership** to the
running user or to Administrators (`/A`) -- it does not grant the original user
the **access** the User Profile Service needs, and the `icacls /reset` (or the
Explorer "replace all child permissions" checkbox) that usually follows `takeown`
**strips the profile's private ACL**, which is exactly what makes `UsrClass.dat`
unloadable and triggers the temp profile.

`fixuser` never changes ownership. It only **adds** an ACE (`icacls /grant`),
which is safe and reversible:

```bat
:: undo the grant if you ever need to:
dz safe-icacls "C:\Users\localuser" /remove "*<SID>" /T /C
```

## Why `dz safe-icacls` instead of `icacls /T`?

A user profile ships a self-referential junction
(`AppData\Local\Application Data -> AppData\Local`). Plain `icacls <profile> /T`
follows reparse points and **recurses forever** on it. (`takeown /R` happens not
to follow junctions, which is why `takeown` "finishes" while `icacls` hangs --
and is part of why admins reach for `takeown` and break things.) `safe-icacls`
reproduces `/T` but prunes junctions, so the recursive grant terminates.

## Safety

- Read-only by default; `--repair` requires an **elevated** shell and **refuses**
  if the target's hive is loaded (`HKU\<SID>` present).
- Always backs up `ProfileList` (`reg export`) and the pre-change ACLs first, to
  `~/.fixuser/backups/<SID>_<timestamp>/`.
- The ACL change is additive (revert with `icacls /remove`); the registry change
  is restorable from the exported `.reg`.
