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

import hashlib
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

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def pack_header(prev_hash: bytes, txs_hash: bytes,
                timestamp: int, difficulty: int, nonce: int) -> bytes:
    """Serialise a block header into exactly 84 bytes."""
    assert len(prev_hash) == 32, "prev_hash must be 32 bytes"
    assert len(txs_hash)  == 32, "txs_hash must be 32 bytes"
    return struct.pack(HEADER_FORMAT, prev_hash, txs_hash,
                       timestamp, difficulty, nonce)


def unpack_header(raw: bytes) -> dict:
    """Deserialise 84 raw bytes back into header fields."""
    assert len(raw) == 84, f"Expected 84 bytes, got {len(raw)}"
    prev_hash, txs_hash, timestamp, difficulty, nonce = \
        struct.unpack(HEADER_FORMAT, raw)
    return dict(prev_hash=prev_hash, txs_hash=txs_hash,
                timestamp=timestamp, difficulty=difficulty, nonce=nonce)


def block_hash(prev_hash: bytes, txs_hash: bytes,
               timestamp: int, difficulty: int, nonce: int) -> bytes:
    """SHA-256 over the 84-byte header."""
    return sha256(pack_header(prev_hash, txs_hash, timestamp, difficulty, nonce))


# ---------------------------------------------------------------------------
# Transaction primitives
# ---------------------------------------------------------------------------

def tx_hash(sender_key: bytes, data: bytes,
            timestamp: int, signature: bytes) -> bytes:
    """
    SHA-256(sender_key || data || timestamp_8byte_be || signature)
    Matches the spec's tx_hash formula exactly.
    """
    ts_bytes = struct.pack(">q", timestamp)   # signed 64-bit BE (wire type `q`)
    return sha256(sender_key + data + ts_bytes + signature)


def txs_hash(tx_hashes: list[bytes]) -> bytes:
    """
    Body commitment: SHA-256 over concatenated 32-byte tx hashes.
    Empty block → SHA-256(b"")  (NOT 32 zero bytes).
    """
    return sha256(b"".join(tx_hashes))        # sha256(b"") when list is empty


# ---------------------------------------------------------------------------
# PoW
# ---------------------------------------------------------------------------

def leading_zero_bits(h: bytes) -> int:
    """Count the number of leading zero bits in a 32-byte hash."""
    count = 0
    for byte in h:
        if byte == 0:
            count += 8
        else:
            # Count leading zeros in this byte
            count += 8 - byte.bit_length()
            break
    return count


def satisfies_pow(h: bytes, difficulty: int) -> bool:
    """Return True if hash h has at least `difficulty` leading zero bits."""
    return leading_zero_bits(h) >= difficulty


def mine_block(prev_hash: bytes, tx_hashes: list[bytes],
               difficulty: int, timestamp: int | None = None) -> dict:
    """
    Search for a nonce that satisfies the declared difficulty.

    Returns a dict with all header fields plus the final block_hash.
    The caller is free to set difficulty; 4–8 bits is fast for testing,
    16–20 bits is more realistic but slower.
    """
    if timestamp is None:
        timestamp = int(time.time())

    commitment = txs_hash(tx_hashes)
    nonce = 0
    while True:
        h = block_hash(prev_hash, commitment, timestamp, difficulty, nonce)
        if satisfies_pow(h, difficulty):
            return dict(
                prev_hash  = prev_hash,
                txs_hash   = commitment,
                timestamp  = timestamp,
                difficulty = difficulty,
                nonce      = nonce,
                block_hash = h,
            )
        nonce += 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_block(block: dict, expected_prev_hash: bytes | None = None) -> str | None:
    """
    Validate a block dict (as returned by mine_block or received from a peer).

    Returns None if valid, or a human-readable error string if not.

    Checks:
      1. block_hash == SHA-256(header)
      2. PoW: block_hash has >= difficulty leading zero bits
      3. prev_hash matches expected_prev_hash (if provided)
      4. txs_hash matches recomputed commitment over tx_hashes (if provided)
    """
    h = block_hash(block["prev_hash"], block["txs_hash"],
                   block["timestamp"], block["difficulty"], block["nonce"])

    if h != block["block_hash"]:
        return f"block_hash mismatch: computed {h.hex()}, stored {block['block_hash'].hex()}"

    if not satisfies_pow(h, block["difficulty"]):
        bits = leading_zero_bits(h)
        return (f"PoW not satisfied: hash has {bits} leading zero bits, "
                f"need {block['difficulty']}")

    if expected_prev_hash is not None and block["prev_hash"] != expected_prev_hash:
        return (f"prev_hash mismatch: expected {expected_prev_hash.hex()}, "
                f"got {block['prev_hash'].hex()}")

    # If the caller passes tx_hashes, recompute and compare
    if "tx_hashes" in block:
        computed = txs_hash(block["tx_hashes"])
        if computed != block["txs_hash"]:
            return (f"txs_hash mismatch: recomputed {computed.hex()}, "
                    f"stored {block['txs_hash'].hex()}")

    return None


# ---------------------------------------------------------------------------
# Genesis block
# ---------------------------------------------------------------------------

def make_genesis(difficulty: int = 4, timestamp: int = 1_700_000_000) -> dict:
    """
    Mine a genesis block.

    Use a fixed timestamp so every node in your group produces the
    IDENTICAL genesis block — agree on the value with your teammates
    and hardcode it in your node startup.

    prev_hash = 32 zero bytes (no parent)
    txs_hash  = SHA-256(b"")  (empty block)
    """
    return mine_block(
        prev_hash  = ZERO_HASH,
        tx_hashes  = [],          # empty block → txs_hash = sha256(b"")
        difficulty = difficulty,
        timestamp  = timestamp,
    )


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== block_primitives self-test ===\n")

    # 1. Header size
    print(f"Header size: {HEADER_SIZE} bytes  ✓")

    # 2. txs_hash for empty block
    empty_commitment = txs_hash([])
    print(f"txs_hash(empty): {empty_commitment.hex()}")
    expected_empty = sha256(b"")
    assert empty_commitment == expected_empty, "Empty txs_hash wrong!"
    print("  == sha256(b'')  ✓")

    # 3. leading_zero_bits
    assert leading_zero_bits(b"\x00\x00\xff" + b"\x00" * 29) == 16
    assert leading_zero_bits(b"\x0f" + b"\x00" * 31) == 4
    assert leading_zero_bits(b"\x01" + b"\x00" * 31) == 7
    print("leading_zero_bits: ✓")

    # 4. Mine a genesis block (low difficulty for speed)
    print("\nMining genesis block (difficulty=4)...")
    genesis = make_genesis(difficulty=4, timestamp=1_700_000_000)
    print(f"  nonce      : {genesis['nonce']}")
    print(f"  block_hash : {genesis['block_hash'].hex()}")
    print(f"  leading 0s : {leading_zero_bits(genesis['block_hash'])} bits")
    assert satisfies_pow(genesis["block_hash"], 4), "Genesis PoW failed!"
    print("  PoW satisfied ✓")

    # 5. Validate the genesis block
    err = validate_block(genesis, expected_prev_hash=ZERO_HASH)
    assert err is None, f"validate_block failed: {err}"
    print("validate_block: ✓")

    # 6. Mine a second block on top of genesis
    print("\nMining block 1 (difficulty=4)...")
    # Fake a transaction hash
    fake_tx = tx_hash(
        sender_key = b"sender_pub_key_bytes_here_padded",
        data       = b"hello blockchain",
        timestamp  = 1_700_000_001,
        signature  = b"fake_sig" * 8,
    )
    print(f"  tx_hash    : {fake_tx.hex()}")

    block1 = mine_block(
        prev_hash  = genesis["block_hash"],
        tx_hashes  = [fake_tx],
        difficulty = 4,
        timestamp  = 1_700_000_100,
    )
    print(f"  nonce      : {block1['nonce']}")
    print(f"  block_hash : {block1['block_hash'].hex()}")

    # Attach tx_hashes list so validate_block can check commitment
    block1["tx_hashes"] = [fake_tx]
    err = validate_block(block1, expected_prev_hash=genesis["block_hash"])
    assert err is None, f"validate_block block1 failed: {err}"
    print("validate_block block1: ✓")

    # 7. Tamper check — mutate nonce, expect failure
    bad = dict(block1)
    bad["nonce"] = block1["nonce"] + 1
    err = validate_block(bad)
    assert err is not None, "Should have caught tampered nonce!"
    print(f"\nTamper detection: ✓  ({err[:60]}...)")

    print("\nAll checks passed ✓")