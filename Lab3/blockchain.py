from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import struct
import time
from ipv8.keyvault.crypto import default_eccrypto
from constants import DIFFICULTY, GENESIS_PREV_HASH, GENESIS_TIMESTAMP, GENESIS_DIFFICULTY, GENESIS_NONCE, MAX_TX_HASHES, MY_MEMBER_ID
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
        
        expected_difficulty = GENESIS_DIFFICULTY if self.prev_hash == GENESIS_PREV_HASH else DIFFICULTY
        if self.difficulty != expected_difficulty:
            return False
        
        # Check block pow
        if not check_pow(self.block_hash, self.difficulty):
            return False
        
        # Check block body
        if compute_txs_hash(self.tx_hashes) != self.txs_hash:
            return False
        
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
        self._last_dumped_height: int = -1
        self._dump_dir = Path(__file__).resolve().parent / "chain_dumps"
        self._dump_dir.mkdir(exist_ok=True)

    def dump_snapshot(self) -> None:
        """Write a chain snapshot for the current height."""
        height = self.get_chain_height()
        snapshot_path = self._dump_dir / f"member_{MY_MEMBER_ID}_height_{height}.txt"
        lines = [
            f"member_id={MY_MEMBER_ID}",
            f"height={height}",
            f"block_count={len(self.chain)}",
            "",
        ]

        for idx, block in enumerate(self.chain):
            tx_hashes_hex = ",".join(tx_hash.hex() for tx_hash in block.tx_hashes)
            lines.append(
                "|".join(
                    [
                        f"h={idx}",
                        f"prev={block.prev_hash.hex()}",
                        f"txs_root={block.txs_hash.hex()}",
                        f"ts={block.timestamp}",
                        f"diff={block.difficulty}",
                        f"nonce={block.nonce}",
                        f"hash={block.block_hash.hex()}",
                        f"tx_count={len(block.tx_hashes)}",
                        f"tx_hashes={tx_hashes_hex}",
                    ]
                )
            )

        try:
            snapshot_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._last_dumped_height = height
            print(f"[dump] Wrote blockchain snapshot: {snapshot_path}")
        except OSError as e:
            print(f"[dump] Failed to write blockchain snapshot: {e}")
        
    def get_chain_height(self) -> int:
        return len(self.chain) - 1  # genesis block is height 0
    
    def get_chain_tip(self) -> Block:
        return self.chain[-1]
    
    def get_block(self, height: int) -> Block | None:
        if 0 <= height < len(self.chain):
            return self.chain[height]
        return None
    
    def append_block(self, block: Block) -> bool:
        if self.get_chain_tip().block_hash != block.prev_hash:
            return False
        
        self.chain.append(block)
        height = self.get_chain_height()
        if height > 0 and height % 10 == 0 and height != self._last_dumped_height:
            self.dump_snapshot()
        return True
    
    def mine_block(self) -> Block | None:
        difficulty = DIFFICULTY
        prev_block = self.get_chain_tip()
        prev_hash = prev_block.block_hash
        transactions = self.mempool[:MAX_TX_HASHES]
        tx_hashes = [tx.tx_hash for tx in transactions]
        if len(self.mempool) > MAX_TX_HASHES:
            print(f"Mining block with max {MAX_TX_HASHES} tx hashes; {len(self.mempool) - MAX_TX_HASHES} txs remain in mempool")
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
        if not self.append_block(new_block):
            print("Failed to append mined block to the chain")
            self.mempool.extend(transactions)
            return None

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