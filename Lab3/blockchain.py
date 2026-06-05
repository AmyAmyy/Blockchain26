from dataclasses import dataclass, field
from hashlib import sha256
import struct
import time
from ipv8.keyvault.crypto import default_eccrypto
from constants import DIFFICULTY, GENESIS_PREV_HASH, GENESIS_TIMESTAMP, GENESIS_DIFFICULTY, GENESIS_NONCE
from helpers import mine, compute_block_hash, compute_txs_hash, check_pow

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
        self.chain: list[Block] = [self.make_genesis()]
        self.mempool: list[Transaction] = []
        
    def get_chain_height(self) -> int:
        return len(self.chain) - 1  # genesis block is height 0
    
    def get_block(self, height: int) -> Block | None:
        if 0 <= height < len(self.chain):
            return self.chain[height]
        return None
    
    def append_block(self, block: Block):
        self.chain.append(block)
    
    def mine_block(self) -> Block:
        difficulty = DIFFICULTY
        prev_block = self.chain[-1]
        prev_hash = prev_block.block_hash
        tx_hashes = [tx.tx_hash for tx in self.mempool]
        del self.mempool[:len(tx_hashes)]
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
        # TODO niet meteen block toevoegen maar eerst checken
        self.chain.append(new_block)

        print(f"Mined new block at height {self.get_chain_height()} with {len(tx_hashes)} transactions")
        
        return new_block
    
    def make_genesis(self) -> Block:
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