#!/usr/bin/env python3
"""
scripts/stream_mint_backfill.py

Streams a zstd-compressed TAR archive (`data/data.tar.zst`) containing prediction
market parquet files, mints GYST UUIDv8 checkpoints, and extracts/processes output
into `data/minted_parquet/`.

Resumption & Fault Tolerance:
- Tracks progress in `data/.backfill_checkpoint.txt` using GYST UUIDv8 strings.
- On restart, skips completed files instantly without re-processing or re-extracting bytes.
- Catches per-file zstd/tar errors so frame corruption won't crash the entire job.
"""

import sys
import tarfile
from pathlib import Path

import zstandard as zstd

# Anchor script paths relative to the Project Root (1 directory up from scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Ensure project root is in sys.path so uuid_service_turboquant can be imported
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uuid_service_turboquant import encode_poly_market_uuid

# --- CONFIGURATION ---
ARCHIVE_PATH = PROJECT_ROOT / "data" / "data.tar.zst"
OUTPUT_DIR = PROJECT_ROOT / "data" / "minted_parquet"
CHECKPOINT_FILE = PROJECT_ROOT / "data" / ".backfill_checkpoint.txt"
BATCH_REPORT_EVERY = 100


def load_checkpoint_uuids() -> set[str]:
    """Load set of completed GYST UUIDv8 strings from the checkpoint file."""
    if not CHECKPOINT_FILE.exists():
        return set()

    with open(CHECKPOINT_FILE, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_checkpoint_uuid(uuid_str: str) -> None:
    """Append a newly completed GYST UUIDv8 string to disk atomically."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{uuid_str}\n")


def stream_mint_backfill():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load existing checkpoint state
    completed_uuids = load_checkpoint_uuids()
    print(f"[*] Loaded {len(completed_uuids)} completed GYST UUIDv8 checkpoints.")

    if not ARCHIVE_PATH.exists():
        print(f"[!] Archive not found at {ARCHIVE_PATH}")
        print(f"    Expected compressed archive at: {ARCHIVE_PATH}")
        sys.exit(1)

    # 2. Setup zstandard streaming decompressor
    dctx = zstd.ZstdDecompressor()

    processed_count = 0
    skipped_count = 0
    minted_count = 0

    print(f"[*] Opening archive stream: {ARCHIVE_PATH}")

    with open(ARCHIVE_PATH, "rb") as fh:
        with dctx.stream_reader(fh) as zstream:
            try:
                # ignore_zeros=True skips empty padding blocks between tar members
                with tarfile.open(fileobj=zstream, mode="r|*", ignore_zeros=True) as tar:
                    for member in tar:
                        # Skip directories or empty blocks
                        if not member or not member.isfile():
                            continue

                        member_name = Path(member.name).name
                        if not member_name.endswith(".parquet"):
                            continue

                        # Generate deterministic GYST UUIDv8 for this dataset member (Type 0x3A0)
                        file_uuid = encode_poly_market_uuid(
                            market_id=f"backfill:{member_name}",
                            confidence=1.0
                        )

                        target_path = OUTPUT_DIR / member_name

                        # 3. FAST SKIP: Check if already processed or already written
                        if file_uuid in completed_uuids or target_path.exists():
                            skipped_count += 1
                            if (skipped_count + minted_count) % BATCH_REPORT_EVERY == 0:
                                print(f"[*] Progress: {minted_count} minted, {skipped_count} skipped...")
                            continue

                        # 4. PROCESS / MINT FILE
                        try:
                            f = tar.extractfile(member)
                            if f is None:
                                continue

                            payload = f.read()

                            # Write parquet chunk using temporary file for atomic write
                            tmp_target_path = target_path.with_suffix(".tmp")
                            with open(tmp_target_path, "wb") as out_f:
                                out_f.write(payload)
                            tmp_target_path.replace(target_path)

                            # 5. COMMIT CHECKPOINT
                            append_checkpoint_uuid(file_uuid)
                            completed_uuids.add(file_uuid)

                            minted_count += 1
                            processed_count += 1

                            print(f"   [+] [{minted_count}] Minted {member_name} -> UUID: {file_uuid}")

                        except (OSError, zstd.ZstdError, tarfile.TarError, Exception) as err:
                            print(f"   [!] Error extracting member {member.name}: {err}")
                            # Record failed member as completed to prevent infinite retry loop
                            append_checkpoint_uuid(file_uuid)
                            completed_uuids.add(file_uuid)
                            continue

            except zstd.ZstdError as err:
                print(f"\n[!] Encountered unrecoverable Zstandard frame corruption: {err}")
                print("[*] Stream paused. Re-run script to resume from checkpoint.")

    print("\n" + "=" * 60)
    print("[*] Backfill Stream Run Complete.")
    print(f"    - Total Minted : {minted_count}")
    print(f"    - Total Skipped: {skipped_count}")
    print(f"    - Checkpoints  : {len(completed_uuids)} active UUIDs")
    print("=" * 60)


if __name__ == "__main__":
    stream_mint_backfill()
