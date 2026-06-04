import argparse
import platform
import re
import subprocess
import tempfile

_DEVICE_SECTION = """
Section "Device"
    Identifier     "Device{device_id}"
    Driver         "nvidia"
    VendorName     "NVIDIA Corporation"
    BusID          "{bus_id}"
EndSection
"""

_SCREEN_SECTION = """
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

_LAYOUT_SECTION = """
Section "ServerLayout"
    Identifier     "Layout0"
    {screen_records}
EndSection
"""


def pci_records() -> list[dict[str, str]]:
    """Return one dict per PCI device from `lspci -vmm`.

    `lspci -vmm` prints device blocks separated by blank lines; each line is
    'Key:\\tValue'. We strip the trailing colon from each key.
    """
    output = subprocess.check_output(["lspci", "-vmm"], text=True)
    records = []
    for block in output.strip().split("\n\n"):
        record = {}
        for line in block.splitlines():
            key, _, value = line.partition("\t")
            record[key.removesuffix(":")] = value
        records.append(record)
    return records


def to_xorg_bus_id(slot: str) -> str:
    """Convert an lspci slot like '65:00.0' to an Xorg BusID like 'PCI:101:0:0'.

    lspci prints the slot in hex (bus:device.function); Xorg wants the same
    numbers in decimal, colon-separated, prefixed with 'PCI:'.
    """
    parts = re.split(r"[:.]", slot)
    return "PCI:" + ":".join(str(int(part, 16)) for part in parts)


def nvidia_bus_ids() -> list[str]:
    """Find the Xorg BusIDs of every NVIDIA display/3D device on the machine."""
    graphics_classes = {"VGA compatible controller", "3D controller"}
    bus_ids = []
    for record in pci_records():
        is_nvidia = record.get("Vendor") == "NVIDIA Corporation"
        is_graphics = record.get("Class") in graphics_classes
        if is_nvidia and is_graphics:
            bus_ids.append(to_xorg_bus_id(record["Slot"]))
    return bus_ids


def generate_xorg_conf(bus_ids: list[str]) -> str:
    """Build an xorg.conf with one Device+Screen per GPU and a single layout."""
    sections = []
    screen_entries = []
    for index, bus_id in enumerate(bus_ids):
        sections.append(_DEVICE_SECTION.format(device_id=index, bus_id=bus_id))
        sections.append(_SCREEN_SECTION.format(device_id=index, screen_id=index))
        screen_entries.append(f'Screen {index} "Screen{index}" 0 0')
    sections.append(_LAYOUT_SECTION.format(screen_records="\n    ".join(screen_entries)))
    return "\n".join(sections)


def run_xorg(config_path: str, display: int) -> None:
    """Run Xorg against the given config until it exits, killing it on interrupt."""
    command = [
        "Xorg",
        "-noreset",
        "+extension",
        "GLX",
        "+extension",
        "RANDR",
        "+extension",
        "RENDER",
        "-config",
        config_path,
        f":{display}",
    ]
    with subprocess.Popen(command) as proc:
        try:
            proc.wait()
        except BaseException:
            proc.kill()
            raise


def start_xorg(display: int = 0) -> None:
    if platform.system() != "Linux":
        raise RuntimeError("Xorg can only be started on Linux")

    bus_ids = nvidia_bus_ids()
    if not bus_ids:
        raise RuntimeError("No NVIDIA graphics devices found")

    with tempfile.NamedTemporaryFile("w", suffix="-xorg.conf") as config_file:
        config_file.write(generate_xorg_conf(bus_ids))
        config_file.flush()  # Xorg reads the path from another process
        run_xorg(config_file.name, display)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start a headless Xorg server bound to the machine's NVIDIA GPUs."
    )
    parser.add_argument(
        "display", nargs="?", type=int, default=0, help="X display number to start (default: 0)"
    )
    args = parser.parse_args()
    start_xorg(args.display)


if __name__ == "__main__":
    main()
