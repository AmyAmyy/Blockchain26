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
import random
import struct
import time
from typing import TYPE_CHECKING

from constants import MAX_TX_HASHES, NONCE_SPACE

if TYPE_CHECKING:
    from blockchain import Block

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
    nonce = random.randint(0, NONCE_SPACE - 1)
    while True:
        h = compute_block_hash(prev_hash, commitment, timestamp, difficulty, nonce)
        if check_pow(h, difficulty):
            return nonce
        nonce = (nonce + 1) % NONCE_SPACE

def extract_ith_block_from_payload(payload, i: int) -> "Block | None":
        # payload.num_blocks: int
        # payload.blocks_data: bytes
        # Returns Block or None
        if i < 0 or i >= payload.num_blocks:
            return None

        data = payload.blocks_data
        offset = 0

        for idx in range(payload.num_blocks):
            # Fixed-size part: 32+32+8+4+8+32+2 = 118 bytes, plus fixed tx hash slots
            if len(data) - offset < 118 + MAX_TX_HASHES * 32:
                return None

            prev_hash = data[offset:offset + 32]
            offset += 32

            txs_hash = data[offset:offset + 32]
            offset += 32

            timestamp = int.from_bytes(data[offset:offset + 8], "big", signed=True)
            offset += 8

            difficulty = int.from_bytes(data[offset:offset + 4], "big", signed=False)
            offset += 4

            nonce = int.from_bytes(data[offset:offset + 8], "big", signed=True)
            offset += 8

            block_hash = data[offset:offset + 32]
            offset += 32

            tx_count = int.from_bytes(data[offset:offset + 2], "big")
            offset += 2

            if tx_count < 0 or tx_count > MAX_TX_HASHES:
                return None

            if len(data) - offset < MAX_TX_HASHES * 32:
                return None

            tx_hashes = []
            for _ in range(tx_count):
                tx_hashes.append(data[offset:offset + 32])
                offset += 32

            offset += (MAX_TX_HASHES - tx_count) * 32

            if idx == i:
                from blockchain import Block

                return Block(
                    prev_hash=prev_hash,
                    txs_hash=txs_hash,
                    timestamp=timestamp,
                    difficulty=difficulty,
                    nonce=nonce,
                    block_hash=block_hash,
                    tx_hashes=tx_hashes,
                )

        return None