# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


import atexit
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile


def pci_records():
    records = []
    command = shlex.split("lspci -vmm")
    output = subprocess.check_output(command).decode()

    for devices in output.strip().split("\n\n"):
        record = {}
        records.append(record)
        for row in devices.split("\n"):
            key, value = row.split("\t")
            record[key.split(":")[0]] = value

    return records


def generate_xorg_conf(devices):
    xorg_conf = []

    device_section = """
Section "Device"
    Identifier     "Device{device_id}"
    Driver         "nvidia"
    VendorName     "NVIDIA Corporation"
    BusID          "{bus_id}"
EndSection
"""
    server_layout_section = """
Section "ServerLayout"
    Identifier     "Layout0"
    {screen_records}
EndSection
"""
    screen_section = """
Section "Screen"
    Identifier     "Screen{screen_id}"
    Device         "Device{device_id}"
    DefaultDepth    24
    Option         "AllowEmptyInitialConfiguration" "True"
    SubSection     "Display"
        Depth       24
        Virtual 1024 768
    EndSubSection
EndSection
"""
    screen_records = []
    for i, bus_id in enumerate(devices):
        xorg_conf.append(device_section.format(device_id=i, bus_id=bus_id))
        xorg_conf.append(screen_section.format(device_id=i, screen_id=i))
        screen_records.append(f'Screen {i} "Screen{i}" 0 0')

    xorg_conf.append(server_layout_section.format(screen_records="\n    ".join(screen_records)))

    output = "\n".join(xorg_conf)
    return output


def startx(display):
    if platform.system() != "Linux":
        raise Exception("Can only run startx on linux")  # noqa: TRY002

    devices = []
    for r in pci_records():
        if r.get("Vendor", "") == "NVIDIA Corporation" and r["Class"] in [
            "VGA compatible controller",
            "3D controller",
        ]:
            bus_id = "PCI:" + ":".join(str(int(x, 16)) for x in re.split(r"[:\.]", r["Slot"]))
            devices.append(bus_id)

    if not devices:
        raise Exception("no nvidia cards found")  # noqa: TRY002

    try:
        fd, path = tempfile.mkstemp()
        with open(path, "w") as f:  # noqa: PTH123
            f.write(generate_xorg_conf(devices))
        command = shlex.split(
            f"Xorg -noreset +extension GLX +extension RANDR +extension RENDER -config {path} :{display}"
        )
        proc = subprocess.Popen(command)
        atexit.register(lambda: proc.poll() is None and proc.kill())
        proc.wait()
    finally:
        os.close(fd)
        os.unlink(path)  # noqa: PTH108


def main():
    display = 0
    if len(sys.argv) > 1:
        display = int(sys.argv[1])
    startx(display)


if __name__ == "__main__":
    main()
