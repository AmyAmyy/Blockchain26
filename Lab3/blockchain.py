from dataclasses import dataclass, field
from hashlib import sha256
import struct
from ipv8.keyvault.crypto import default_eccrypto

@dataclass
class Block:
    prev_hash: bytes
    txs_hash: bytes
    timestamp: int
    difficulty: int
    nonce: int
    block_hash: bytes
    tx_hashes: list[bytes] = field(default_factory=list)
    
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
        self.chain: list[Block] = []
        self.mempool: list[Transaction] = []
        
    def get_chain_height(self) -> int:
        return len(self.chain) - 1  # genesis block is height 0
    
    def get_block(self, height: int) -> Block | None:
        if 0 <= height < len(self.chain):
            return self.chain[height]
        return None