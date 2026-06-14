# This file has been modified from the original ElasticNotebook.
# Original: https://github.com/illinoisdata/ElasticNotebook

import os
import pickle
import shutil
import time

import numpy as np

# Realistic bounds for the combined read+write speed (bytes/s). Values outside
# this band almost always indicate a measurement artifact rather than the real
# disk/serialization throughput, so they are treated as invalid. See issue #21.
MIN_SPEED_BPS = 1e6  # 1 MB/s  - implausibly slow
MAX_SPEED_BPS = 2e9  # 2 GB/s  - implausibly fast for a write+read round trip
FALLBACK_SPEED_BPS = 5e8  # 500 MB/s - sane default when measurement is invalid


def profile_migration_speed(dirname: str, alpha=1) -> float:
    """
    The migration speed is the combined read+write throughput (we write the state to disk,
    then read it back to restore the notebook). The measurement should be fast (<1 sec).

    Unlike the original implementation, this does NOT use a large-minus-small differencing
    trick: with small test arrays the timing difference is dominated by noise and can become
    near-zero or negative, producing absurd speeds (e.g. 7 GB/s) that make the optimizer
    migrate huge variables and stall the checkpoint (issue #21). Instead we measure a single
    fixed-size array directly and clamp the result to a realistic range.

    Args:
        dirname: Location to profile.
        alpha: Scaling factor applied to the write time relative to the read time.
    """
    testing_dir = os.path.join(dirname, "measure_speed")
    shutil.rmtree(testing_dir, ignore_errors=True)
    os.makedirs(testing_dir)

    try:
        # ~8 MB: large enough that write+read is well above timer resolution
        # (giving a stable measurement) yet small enough to finish in tens of ms.
        write_array = np.random.rand(1000, 1000)
        total_bytes = write_array.nbytes
        path = os.path.join(testing_dir, "probe")

        write_start = time.time()
        with open(path, "wb") as out_file:
            pickle.dump(write_array, out_file)
        write_time = time.time() - write_start

        read_start = time.time()
        with open(path, "rb") as in_file:
            in_file.read()  # actually read the bytes so read speed is measured
        read_time = time.time() - read_start
    finally:
        shutil.rmtree(testing_dir, ignore_errors=True)

    denominator = read_time + write_time * alpha

    # Guard against a zero/negative denominator (timer resolution) and against
    # non-finite or out-of-range results; fall back to a sane default.
    if denominator <= 0:
        return FALLBACK_SPEED_BPS

    migration_speed_bps = total_bytes / denominator
    if not np.isfinite(migration_speed_bps):
        return FALLBACK_SPEED_BPS

    return float(np.clip(migration_speed_bps, MIN_SPEED_BPS, MAX_SPEED_BPS))
