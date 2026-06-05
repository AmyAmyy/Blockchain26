"""
block_primitives.py
===================
Self-contained block primitives for the Lab 3 PoW blockchain.
No IPv8 dependency — import and unit-test freely.

Block header layout (84 bytes, all big-endian):
  prev_hash   32 bytes
  txs_hash    32 bytes
  timestamp    8 bytes  uint64
  difficulty   4 bytes  uint32
  nonce        8 bytes  uint64
"""

from hashlib import sha256
import struct
import time


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADER_FORMAT = ">32s32sQIQ"   # big-endian: 32s 32s uint64 uint32 uint64
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)   # must be 84
assert HEADER_SIZE == 84, f"Header size is {HEADER_SIZE}, expected 84"

ZERO_HASH = b"\x00" * 32      # used as prev_hash of the genesis block


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def compute_block_hash(prev_hash: bytes, txs_hash: bytes, timestamp: int, difficulty: int, nonce: int) -> bytes:
    header = prev_hash + txs_hash + struct.pack(">Q", timestamp) + struct.pack(">I", difficulty) + struct.pack(">Q", nonce) 
    return sha256(header).digest()

def compute_txs_hash(tx_hashes: list[bytes]) -> bytes:
    return sha256(b"".join(tx_hashes)).digest()   # SHA256(b"") for empty block

def check_pow(block_hash: bytes, difficulty: int) -> bool:
    """Return True if block_hash has at least `difficulty` leading zero bits."""
    nr_zero_bytes, leftover = divmod(difficulty, 8)
    if block_hash[:nr_zero_bytes] != b'\x00' * nr_zero_bytes:
        return False
    # Leftover bits in following byte must be zero
    if leftover:
        mask = 0xFF >> leftover
        if block_hash[nr_zero_bytes] & ~mask:
            return False
    return True

def mine(prev_hash: bytes, tx_hashes: list[bytes],
               difficulty: int, timestamp: int | None = None) -> int:
    """
    Search for a nonce that satisfies the declared difficulty.

    Returns the nonce that satisfies the difficulty.
    The caller is free to set difficulty; 4–8 bits is fast for testing,
    16–20 bits is more realistic but slower.
    """
    if timestamp is None:
        timestamp = int(time.time())

    commitment = compute_txs_hash(tx_hashes)
    nonce = 0
    while True:
        h = compute_block_hash(prev_hash, commitment, timestamp, difficulty, nonce)
        if check_pow(h, difficulty):
            return nonce
        nonce += 1


# def validate_block(block: dict, expected_prev_hash: bytes | None = None) -> str | None:
#     """
#     Validate a block dict (as returned by mine_block or received from a peer).

#     Returns None if valid, or a human-readable error string if not.

#     Checks:
#       1. block_hash == SHA-256(header)
#       2. PoW: block_hash has >= difficulty leading zero bits
#       3. prev_hash matches expected_prev_hash (if provided)
#       4. txs_hash matches recomputed commitment over tx_hashes (if provided)
#     """
#     h = compute_block_hash(block["prev_hash"], block["txs_hash"],
#                    block["timestamp"], block["difficulty"], block["nonce"])

#     if h != block["block_hash"]:
#         return f"block_hash mismatch: computed {h.hex()}, stored {block['block_hash'].hex()}"

#     if not check_pow(h, block["difficulty"]):
#         bits = leading_zero_bits(h)
#         return (f"PoW not satisfied: hash has {bits} leading zero bits, "
#                 f"need {block['difficulty']}")

#     if expected_prev_hash is not None and block["prev_hash"] != expected_prev_hash:
#         return (f"prev_hash mismatch: expected {expected_prev_hash.hex()}, "
#                 f"got {block['prev_hash'].hex()}")

#     # If the caller passes tx_hashes, recompute and compare
#     if "tx_hashes" in block:
#         computed = txs_hash(block["tx_hashes"])
#         if computed != block["txs_hash"]:
#             return (f"txs_hash mismatch: recomputed {computed.hex()}, "
#                     f"stored {block['txs_hash'].hex()}")

#     return None