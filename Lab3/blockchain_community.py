import asyncio
from ipv8.community import Community, CommunitySettings
from ipv8.peer import Peer as PeerType
from ipv8.lazy_community import lazy_wrapper
from hashlib import sha256

from message_payloads import (
    GetChainHeight,
    ChainHeightResponse,
    GetBlock,
    BlockResponse,
    SubmitTransaction,
    SubmitTransactionResponse
)
from constants import (
    BLOCKCHAIN_COMMUNITY_ID,
    SERVER_PUBKEY_BYTES,
    GROUP_ID,
    MEMBER_COUNT,
    MY_MEMBER_ID,
    load_member_pubkeys,
)

from blockchain import Transaction, Blockchain

class BlockchainCommunity(Community):
    community_id = BLOCKCHAIN_COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.member_id: int = MY_MEMBER_ID
        self.member_pubkeys: list[bytes] = load_member_pubkeys()
        self.member_peers: list[PeerType | None] = [None] * MEMBER_COUNT
        self._ready_peers: set[int] = {self.member_id}

        self.group_id = GROUP_ID
        self.blockchain = Blockchain()

        self._mining_task: asyncio.Task | None = None

        # Sanity-check: my IPv8 key MUST match the pubkey at MY_MEMBER_ID,
        # otherwise the server will reject every signed packet.
        my_pk = self.my_peer.public_key.key_to_bin()
        expected = self.member_pubkeys[self.member_id]
        if my_pk != expected:
            raise RuntimeError(
                f"MY_MEMBER_ID={self.member_id} but my_peer pubkey does not match "
                f"the expected pubkey for that member ID."
            )
        # I already know my own peer object.
        self.member_peers[self.member_id] = self.my_peer

        self._server_pubkey_bytes = SERVER_PUBKEY_BYTES
        self._server_peer: PeerType | None = None

        self.add_message_handler(SubmitTransaction, self.on_submit_transaction)
        self.add_message_handler(GetChainHeight, self.on_chain_height)
        self.add_message_handler(GetBlock, self.on_get_block)

    def started(self) -> None:
        self.network.add_peer_observer(self)

    def _all_teammembers_known(self) -> bool:
        return all(p is not None for p in self.member_peers)

    # ── peer discovery ──────────────────────────────────────────────────────
    
    def on_peer_added(self, peer: PeerType) -> None:
        pk_bytes = peer.public_key.key_to_bin()
        if pk_bytes == self._server_pubkey_bytes:
            print(f"Found in blockchain community server peer: {peer}")
            self._server_peer = peer

        elif pk_bytes in self.member_pubkeys:
            idx = self.member_pubkeys.index(pk_bytes)
            if self.member_peers[idx] is None:
                print(f"Found in blockchain community team member peer #{idx}: {peer}")
                self.member_peers[idx] = peer
                self._ready_peers.add(idx)
        
        if self._all_teammembers_known() and self._server_peer is not None and self._mining_task is None:
            self._mining_task = asyncio.create_task(self._mining_loop())
            print("All team members and server discovered")
        
    def on_peer_removed(self, peer: PeerType) -> None:
        if self._server_peer is not None and peer == self._server_peer:
            print("⚠️  Server peer disconnected")
            self._server_peer = None
        if peer in self.member_peers:
            idx = self.member_peers.index(peer)
            print(f"⚠️  Team member peer #{idx} disconnected: {peer}")
            self.member_peers[idx] = None
            self._ready_peers.discard(idx)

    @lazy_wrapper(SubmitTransaction)
    def on_submit_transaction(self, peer: PeerType, payload: SubmitTransaction) -> None:
        print("Received transaction")
        transaction = Transaction(
            sender_key = payload.sender_key,
            data = payload.data,
            timestamp = payload.timestamp,
            signature = payload.signature,
        )
        
        if not transaction.verify_signature():
            print("⚠️  Received transaction with invalid signature")
            bundle = SubmitTransactionResponse(
                success = False,
                tx_hash = transaction.tx_hash,
                message = "Invalid transaction signature"
            )
            self.ez_send(peer, bundle)
            return
        
        self.blockchain.mempool.append(transaction)
        print(f"Received valid transaction, mempool size is now {len(self.blockchain.mempool)}")
        bundle = SubmitTransactionResponse(
            success = True,
            tx_hash = transaction.tx_hash,
            message = "Transaction accepted"
        )
        self.ez_send(peer, bundle)
        
    
    @lazy_wrapper(GetChainHeight)
    def on_chain_height(self, peer: PeerType, payload: GetChainHeight) -> None:
        print("Received chain height function")
        height = self.blockchain.get_chain_height()
        tip_hash = self.blockchain.get_block(height).block_hash
        bundle = ChainHeightResponse(
            request_id = payload.request_id,
            height = height,
            tip_hash = tip_hash,
        )
        self.ez_send(peer, bundle)

    @lazy_wrapper(GetBlock)
    def on_get_block(self, peer: PeerType, payload: GetBlock) -> None:
        print(f"Received on get block with height {payload.height}")
        block = self.blockchain.get_block(payload.height)
        if block is None:
            print(f"⚠️  Received GetBlock for invalid height {payload.height}")
            return
        
        bundle = BlockResponse(
            height = payload.height,
            prev_hash = block.prev_hash,
            txs_hash = block.txs_hash,
            timestamp = block.timestamp,
            difficulty = block.difficulty,
            nonce = block.nonce,
            block_hash = block.block_hash,
            tx_hashes = b"".join(block.tx_hashes),
        )
        self.ez_send(peer, bundle)
    
    async def _mining_loop(self) -> None:
        """Mine only when there is at least one transaction in the mempool."""
        print("[mining] Started")

        while True:
            if not self.blockchain.mempool:
                await asyncio.sleep(0.2)
                continue

            try:
                # Mining is CPU-bound, so run it in a worker thread.
                new_block = await asyncio.get_running_loop().run_in_executor(
                    None,
                    self.blockchain.add_block,
                )
                height = self.blockchain.get_chain_height()
                print(
                    f"[mining] Mined block {height} "
                    f"hash={new_block.block_hash.hex()[:16]}... "
                    f"txs={len(new_block.tx_hashes)}"
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[mining] Error: {e}")
                await asyncio.sleep(1)