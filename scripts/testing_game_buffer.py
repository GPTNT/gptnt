import concurrent.futures
import struct
import time

import requests
import structlog
from PIL import Image

logger = structlog.get_logger()

# The URL matching your Unity server
SERVER_URL = "http://localhost:8085/buffer"
SLOW_SERVER_URL = "http://localhost:8085/old-buffer"


def process_and_save_image(raw_bytes, width, height, index):
    """Converts raw RGBA bytes into a PNG and saves it to disk."""
    try:
        # Unity sends raw RGB24 data, which Pillow can read directly
        img = Image.frombytes("RGB", (width, height), raw_bytes)

        # Unity's Y-axis starts at the bottom. Standard images start at the top.
        # We must flip the image vertically so it isn't upside down.
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
        img.save(f"image_{index}.png")
    except Exception as e:  # noqa: BLE001
        return f"Failed to save image {index}: {e}"
    else:
        return f"converted image {index} to PIL format successfully."


def fetch_and_encode_textures():
    logger.info(f"Requesting raw textures from {SERVER_URL}...")
    start_time = time.time()

    try:
        response = requests.get(SERVER_URL)
        response.raise_for_status()  # Raise an error if the HTTP request fails
    except requests.exceptions.RequestException as e:
        logger.exception("Connection error. Is the game running?", error=e)
        return None

    fetch_time = time.time() - start_time
    data = response.content
    logger.info(f"Received {len(data):,} bytes in {fetch_time:.3f} seconds.")

    # 1. Parse the Header
    # C# BinaryWriter defaults to Little-Endian. '<iii' means three standard 4-byte integers.
    try:
        includes_segmentation, num_images, height, width = struct.unpack("<biii", data[:13])
    except struct.error:
        logger.exception("Failed to parse the 13-byte header. Check the Unity server payload.")
        return None

    logger.info(
        f"Header parsed: {num_images} images, {width}x{height} resolution. Includes segmentation: {bool(includes_segmentation)}"
    )

    bytes_per_image = width * height * 3  # 4 bytes per pixel (RGBA32)
    expected_payload_size = 13 + (num_images * bytes_per_image)

    if len(data) < expected_payload_size:
        logger.error(
            f"Error: Incomplete payload. Expected {expected_payload_size:,} bytes, got {len(data):,}."
        )
        return None

    # 2. Slice the payload into separate byte arrays for each image
    image_chunks = []
    current_offset = 13
    for _ in range(num_images + (1 if includes_segmentation else 0)):
        chunk = data[current_offset : current_offset + bytes_per_image]
        image_chunks.append(chunk)
        current_offset += bytes_per_image

    # 3. Encode in parallel using multiprocessing
    logger.info("Encoding images in parallel...")
    encode_start = time.time()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit all images to the process pool
        futures = [
            executor.submit(process_and_save_image, image_chunks[i], width, height, i)
            for i in range(num_images)
        ]
        if includes_segmentation:
            futures.append(
                executor.submit(
                    process_and_save_image, image_chunks[-1], width, height, "segmentation"
                )
            )

        # Print results as they finish
        for _future in concurrent.futures.as_completed(futures):
            # logger.info(_future.result())
            continue

    encode_time = time.time() - encode_start
    total_time = time.time() - start_time
    logger.info(f"Finished encoding {num_images} images in {encode_time:.3f} seconds.")
    logger.info(f"Total round-trip time: {total_time:.3f} seconds.")
    return total_time


def fetch_slow_base64_strings():
    logger.info(f"Requesting slow base64 PNGs from {SLOW_SERVER_URL}...")
    start_time = time.time()

    try:
        response = requests.get(SLOW_SERVER_URL)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.exception("Connection error", error=e)
        return None

    fetch_time = time.time() - start_time

    logger.info(f"Received old in {fetch_time:.3f} seconds.")

    # Decode and save
    save_start = time.time()

    save_time = time.time() - save_start
    total_time = time.time() - start_time

    logger.info(f"Finished saving to disk in {save_time:.3f} seconds.")
    logger.info(f"Total round-trip time: {total_time:.3f} seconds.")
    return total_time


if __name__ == "__main__":
    logger.info("--- Testing FAST Raw Dump ---")
    fast = fetch_and_encode_textures()
    time.sleep(2)  # Short pause between tests
    logger.info("--- Testing SLOW Base64 Endpoint ---")
    slow = fetch_slow_base64_strings()

    if fast is not None and slow is not None:
        logger.info(f"faster by {slow - fast:.3f} seconds ({(slow - fast) / slow * 100:.1f}%)")
