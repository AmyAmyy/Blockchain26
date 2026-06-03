from dataclasses import dataclass, field
from hashlib import sha256
import struct
import time
from ipv8.keyvault.crypto import default_eccrypto
from constants import GENESIS_PREV_HASH, GENESIS_TIMESTAMP, GENESIS_DIFFICULTY, GENESIS_NONCE
from helpers import mine, mine_block, txs_hash

# ── helpers ─────────────────────────────────────────────────────────────
    
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

def compute_txs_hash(tx_hashes: list[bytes]) -> bytes:
    return sha256(b"".join(tx_hashes)).digest()   # SHA256(b"") for empty block

def compute_block_hash(prev_hash: bytes, txs_hash: bytes, timestamp: int, difficulty: int, nonce: int) -> bytes:
    header = prev_hash + txs_hash + struct.pack(">Q", timestamp) + struct.pack(">I", difficulty) + struct.pack(">Q", nonce) 
    return sha256(header).digest()

# ── Block  ─────────────────────────────────────────────────────────────

@dataclass
class Block:
    prev_hash: bytes
    txs_hash: bytes
    timestamp: int
    difficulty: int
    nonce: int
    block_hash: bytes
    tx_hashes: list[bytes] = field(default_factory=list)

    def verify_block(self) -> bool:
        # Check block hash
        expected_hash = compute_block_hash(
            self.prev_hash, self.txs_hash,
            self.timestamp, self.difficulty, self.nonce
        )
        if expected_hash != self.block_hash:
            return False
        
        # Check block pow
        if not check_pow(self.block_hash, self.difficulty):
            return False
        
        # Check block body
        if compute_txs_hash(self.tx_hashes) != self.txs_hash:
            return False
        
        # Check previous block
        # TODO but maybe not in this function
        
        return True
    
    
def make_genesis() -> Block:
    txs_hash = compute_txs_hash([])   # SHA256(b"")
    nonce = GENESIS_NONCE
    block_hash = compute_block_hash(
        GENESIS_PREV_HASH, txs_hash,
        GENESIS_TIMESTAMP, GENESIS_DIFFICULTY, nonce
    )

    return Block(
        prev_hash  = GENESIS_PREV_HASH,
        txs_hash   = txs_hash,
        timestamp  = GENESIS_TIMESTAMP,
        difficulty = GENESIS_DIFFICULTY,
        nonce      = nonce,
        block_hash = block_hash,
        tx_hashes  = [],
    )
    
# ── Transaction  ─────────────────────────────────────────────────────────────
    
@dataclass
class Transaction:
    sender_key: bytes
    data: bytes
    timestamp: int
    signature: bytes
    
    @property
    def tx_hash(self) -> bytes:
        ts_bytes = struct.pack(">q", self.timestamp)   # signed 64-bit BE (wire type `q`)
        return sha256(self.sender_key + self.data + ts_bytes + self.signature).digest()
    
    def verify_signature(self) -> bool:
        """Verify the transaction signature using IPv8 crypto."""
        # The signed message is: sender_key || data || timestamp_8byte_be
        message = self.sender_key + self.data + struct.pack(">q", self.timestamp)
        try:
            key = default_eccrypto.key_from_public_bin(self.sender_key)
            return default_eccrypto.is_valid_signature(key, message, self.signature)
        except Exception:
            return False
    
class Blockchain:
    def __init__(self):
        self.chain: list[Block] = [make_genesis()]
        self.mempool: list[Transaction] = []
        
    def get_chain_height(self) -> int:
        return len(self.chain) - 1  # genesis block is height 0
    
    def get_block(self, height: int) -> Block | None:
        if 0 <= height < len(self.chain):
            return self.chain[height]
        return None
    
    def add_block(self, difficulty: int) -> Block:
        prev_block = self.chain[-1]
        prev_hash = prev_block.block_hash
        tx_hashes = [tx.tx_hash for tx in self.mempool]
        self.mempool.remove(0, len(self.mempool))
        timestamp = int(time.time())

        mined_nonce = mine(prev_hash, tx_hashes, difficulty, timestamp)
    
        txs_hash = compute_txs_hash(tx_hashes)
        block_hash = compute_block_hash(prev_hash, txs_hash, timestamp, difficulty, mined_nonce)

        new_block = Block(
            prev_hash = prev_hash,
            txs_hash = txs_hash,
            timestamp = timestamp,
            difficulty = difficulty,
            nonce = mined_nonce,
            block_hash = block_hash,
            tx_hashes = tx_hashes,
        )
        
        # Add to chain and clear mempool
        self.chain.append(new_block)

        print(f"Mined new block at height {self.get_chain_height()} with {len(tx_hashes)} transactions")
        
        return new_block