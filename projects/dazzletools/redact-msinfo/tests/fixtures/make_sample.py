"""
Regenerate ``sample_msinfo.txt`` -- a synthetic msinfo32 export used by the
redact-msinfo tests and human checklist.

The file mimics what Windows msinfo32 "Export" produces: UTF-16 LE, CRLF line
endings, [Section] headers, an "Item<TAB>Value" header in System Summary, and
TAB-separated key/value rows. All identifiers are obviously fake (TESTHOST01,
192.168.x, sk-test-EXAMPLE...) so the file is safe to commit to a public repo.

Run:  python make_sample.py
"""

import io
import os

# Hostname used throughout; pass `--hostname TESTHOST01` to redact-msinfo when
# testing against this file (auto-detect would look for the real machine name).
HOST = "TESTHOST01"

ROWS = [
    "System Information report written at: 05/29/2026 12:00:00",
    "[System Summary]",
    "",
    "Item\tValue\t",
    # OS identity (surfaced first by the reorder)
    "OS Name\tMicrosoft Windows 11 Pro\t",
    "Version\t10.0.26100 Build 26100\t",
    "OS Manufacturer\tMicrosoft Corporation\t",
    "System Type\tx64-based PC\t",
    "Locale\tUnited States\t",
    "Time Zone\tPacific Standard Time\t",
    # Hardware identity
    "System Manufacturer\tTest Systems Inc.\t",
    "System Model\tTestModel X1\t",
    "Processor\tTest CPU @ 3.00GHz, 8 Core(s)\t",
    "BIOS Version/Date\tTestBIOS 1.0, 1/1/2026\t",
    "SMBIOS Version\t3.5\t",
    "BaseBoard Manufacturer\tTest Boards\t",
    "Secure Boot State\tOn\t",
    # PII rows (must be scrubbed in output)
    "System Name\t" + HOST + "\t",
    "User Name\t" + HOST + "\\testuser\t",
    "Registered Owner\tTest Owner\t",
    "Registered Organization\tTest Org LLC\t",
    "Windows Product ID\t00330-00000-00000-AA000\t",
    "Product Key\tAAAAA-BBBBB-CCCCC-DDDDD-EEEEE\t",
    "System UUID\t12345678-1234-1234-1234-123456789ABC\t",
    "Serial Number\tSN-TEST-123456\t",
    "Windows Directory\tC:\\Users\\testuser\\AppData\t",
    "[Display]",
    "",
    "Item\tValue\t",
    "Name\tTest GPU 9000\t",
    "Adapter RAM\t8.00 GB (8,589,934,592 bytes)\t",
    "Driver Version\t30.0.0.1\t",
    "[Problem Devices]",
    "",
    "Device\tPNP Device ID\tError code\t",
    "Test Problem Device\tPCI\\VEN_0000\tThis device is not working.\t",
    "[System Drivers]",
    "",
    "Name\tDescription\tFile\tType\t",
    "testdrv\tTest Driver\tc:\\windows\\system32\\drivers\\testdrv.sys (host " + HOST + ")\tKernel\t",
    "[Environment Variables]",
    "",
    "Variable\tValue\tUser Name\t",
    "FAKE_API_KEY\tsk-test-EXAMPLE-NOT-A-REAL-KEY-000\t" + HOST + "\\testuser\t",
    "Path\tC:\\Users\\testuser\\bin\t" + HOST + "\\testuser\t",
    "[Network]",
    "[Adapter]",
    "",
    "Name\t[00000003] Test NIC\t",
    "Adapter Type\tEthernet 802.3\t",
    "MAC Address\t00:11:22:33:44:55\t",
    "IP Address\t192.168.1.50\t",
    "IP Subnet\t255.255.255.0\t",
    "DHCP Server\t192.168.1.1\t",
    "[Services]",
    "",
    "Display Name\tName\tState\tStart Mode\t",
    "Test Service\tTestSvc\tRunning\tAuto\t",
    "[Drives]",
    "",
    "Drive\tC:\t",
    "Volume Serial Number\t1A2B3C4D\t",
    "[Program Groups]",
    "",
    "Group Name\tUser Name\t",
    "Startup\tAll Users\t",
]


def build_sample():
    """Return the sample content as a single CRLF-joined string."""
    return "\r\n".join(ROWS) + "\r\n"


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_msinfo.txt")
    with io.open(out_path, "w", encoding="utf-16", newline="") as fh:
        fh.write(build_sample())
    print("wrote", out_path)
    print("rows:", len(ROWS), "| hostname:", HOST)


if __name__ == "__main__":
    main()
