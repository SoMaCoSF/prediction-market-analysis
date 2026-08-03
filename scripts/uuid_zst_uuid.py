# stream_backfill.py - Zero-Disk-Space Parquet Ingestion
import tarfile

import duckdb
import zstandard as zstd

zst_path = r"D:\somacosf\outputs\prediction-market-analysis\data\data.tar.zst"

# 1. Open Zstandard streaming reader
with open(zst_path, "rb") as fh:
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(fh) as stream:
        # 2. Wrap stream in tarfile
        with tarfile.open(fileobj=stream, mode="r|*") as tar:
            for member in tar:
                # Process only Kalshi / Polymarket parquet files one by one
                if member.isfile() and member.name.endswith(".parquet"):
                    print(f"Processing in-memory: {member.name}")

                    # Read file directly from memory stream
                    file_bytes = tar.extractfile(member).read()

                    # Query parquet in memory with DuckDB
                    con = duckdb.connect()
                    df = con.execute("SELECT * FROM read_parquet(?)", [file_bytes]).df()

                    # TODO: Pass df rows to your UUID minter (mintUUID) & write to Turso/DB

                    # Memory is automatically freed for the next file!
