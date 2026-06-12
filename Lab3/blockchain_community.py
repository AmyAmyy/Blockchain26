import asyncio
from ipv8.community import Community, CommunitySettings
from ipv8.peer import Peer as PeerType
from ipv8.lazy_community import lazy_wrapper

from message_payloads import (
    GetChainHeight,
    ChainHeightResponse,
    GetBlock,
    BlockResponse,
    GetMultipleBlocks,
    MultipleBlocksResponse,
    MultipleBlocksResponse,
    SubmitTransaction,
    SubmitTransactionResponse
)
from constants import (
    BLOCKCHAIN_COMMUNITY_ID,
    SERVER_PUBKEY_BYTES,
    GROUP_ID,
    MEMBER_COUNT,
    MY_MEMBER_ID,
    MAX_TX_HASHES,
    load_member_pubkeys,
)

from blockchain import Transaction, Blockchain, Block

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
        self.add_message_handler(BlockResponse, self.on_block_response)
        self.add_message_handler(GetMultipleBlocks, self.on_get_multiple_blocks)
        self.add_message_handler(MultipleBlocksResponse, self.on_multiple_blocks_response)

    def started(self) -> None:
        self.network.add_peer_observer(self)

    def _all_teammembers_known(self) -> bool:
        return all(p is not None for p in self.member_peers)
    
    def from_server_or_teammate(self, peer: PeerType) -> bool:
        if self._server_peer is not None and peer == self._server_peer:
            return True
        if peer in self.member_peers:
            return True
        print("⚠️  Received message from unknown peer, ignoring")
        return False
    
    def broadcast_block(self, new_block: Block) -> None:
        bundle = BlockResponse(
            height = self.blockchain.get_chain_height(),
            prev_hash = new_block.prev_hash,
            txs_hash = new_block.txs_hash,
            timestamp = new_block.timestamp,
            difficulty = new_block.difficulty,
            nonce = new_block.nonce,
            block_hash = new_block.block_hash,
            tx_hashes = b"".join(new_block.tx_hashes),
        )

        for peer in self.member_peers:
            if peer is not None and peer != self.my_peer:
                self.ez_send(peer, bundle)

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
        '''Handle a SubmitTransaction message from server. Validate the transaction and add it to the mempool if valid.'''
        print("RECEIVED SUBMIT TRANSACTION")
        
        if not self.from_server_or_teammate(peer):
            return

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
        
        print(f"Add transaction to mempool")
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
        '''Handle a GetChainHeight message from server or peer. Respond with the current chain height and tip hash.'''
        print("Received chain height function")
        
        if not self.from_server_or_teammate(peer):
            return
        
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
        # print(f"Received on get block with height {payload.height}")
        
        if not self.from_server_or_teammate(peer):
            return

        block = self.blockchain.get_block(payload.height)
        if block is None:
            print(f"⚠️  Received GetBlock for invalid height {payload.height}")
            return
        
        tx_count = len(block.tx_hashes)
        if tx_count > MAX_TX_HASHES:
            print(f"Cannot serve GetBlock: block at height {payload.height} has too many tx hashes ({tx_count}), max is {MAX_TX_HASHES}")
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
    
    @lazy_wrapper(BlockResponse)
    def on_block_response(self, peer: PeerType, payload: BlockResponse) -> None:
        print(f"Received block")
        
        if not self.from_server_or_teammate(peer):
            return

        if len(payload.tx_hashes) % 32 != 0:
            print("Received BlockResponse with invalid tx_hashes length")
            return
        payload_tx_count = len(payload.tx_hashes) // 32
        if payload_tx_count > MAX_TX_HASHES:
            print(f"Received BlockResponse with too many tx hashes ({payload_tx_count}), max is {MAX_TX_HASHES}")
            return

        block = Block(
            prev_hash=payload.prev_hash,
            txs_hash=payload.txs_hash,
            timestamp=payload.timestamp,
            difficulty=payload.difficulty,
            nonce=payload.nonce,
            block_hash=payload.block_hash,
            tx_hashes=[payload.tx_hashes[i:i + 32] for i in range(0, len(payload.tx_hashes), 32)],
        )

        if not block.verify_block():
            print(f"NOT GOOD, block wrong")
            return
        
        if payload.height <= self.blockchain.get_chain_height():
            print(f"too far behind or same height")
            return
        
        if payload.height - 1 > self.blockchain.get_chain_height(): # update own chain
            print(f"Missing blocks, requesting from server starting at height {self.blockchain.get_chain_height() + 1}")
            bundle = GetMultipleBlocks(
                start_height = self.blockchain.get_chain_height() + 1
            )
            self.ez_send(peer, bundle)
            return
        
        if not self.blockchain.append_block(block):
            # TODO sync strategy
            print(f"Failed to append block at height {payload.height}, maybe due to mismatched prev_hash?")
        print(f"Added block at height {payload.height} to the chain")
        print(f"Chain height is now {self.blockchain.get_chain_height()}")
    
    @lazy_wrapper(GetMultipleBlocks)
    def on_get_multiple_blocks(self, peer: PeerType, payload: GetMultipleBlocks) -> None:
        print(f"Received request for multiple blocks starting at height {payload.start_height}")
        
        if not self.from_server_or_teammate(peer):
            return
        
        start = payload.start_height
        if start < 0 or start > self.blockchain.get_chain_height():
            print(f"Invalid start height {start} for GetMultipleBlocks")
            return
        
        blocks_data = b""
        num_blocks = 0
        for height in range(start, self.blockchain.get_chain_height() + 1):
            block = self.blockchain.get_block(height)
            if block is None:
                print(f"Unexpectedly missing block at height {height} when preparing MultipleBlocksResponse")
                return
            
            blocks_data += block.prev_hash
            blocks_data += block.txs_hash
            blocks_data += block.timestamp.to_bytes(8, "big", signed=True)
            blocks_data += block.difficulty.to_bytes(8, "big", signed=True)
            blocks_data += block.nonce.to_bytes(8, "big", signed=True)
            blocks_data += block.block_hash
            tx_count = len(block.tx_hashes)
            if tx_count > MAX_TX_HASHES:
                print(f"Block at height {height} has too many tx hashes ({tx_count}), max is {MAX_TX_HASHES}")
                return
            blocks_data += tx_count.to_bytes(2, "big")
            for tx_hash in block.tx_hashes:
                blocks_data += tx_hash
            blocks_data += b"\x00" * ((MAX_TX_HASHES - tx_count) * 32)
            
            num_blocks += 1
        
        bundle = MultipleBlocksResponse(
            start_height = start,
            num_blocks = num_blocks,
            blocks_data = blocks_data,
        )
        self.ez_send(peer, bundle)

    @lazy_wrapper(MultipleBlocksResponse)
    def on_multiple_blocks_response(self, peer: PeerType, payload: MultipleBlocksResponse) -> None:
        print(f"Received blocksss")
        
        if not self.from_server_or_teammate(peer):
            return
        
        if payload.start_height - 1 > self.blockchain.get_chain_height():
            print(f"Missing blocks, cannot add block at height {payload.start_height}")
            return

        for i in range(payload.num_blocks):
            block = self.extract_ith_block_from_payload(payload, i)
            if block is None:
                print(f"Failed to parse block index {i} from MultipleBlocksResponse")
                return

            if not block.verify_block():
                print(f"NOT GOOD, block wrong")
                return
            
            if payload.start_height + i <= self.blockchain.get_chain_height():
                print(f"Block at height {payload.start_height + i} already exists")
                return
            
            if not self.blockchain.append_block(block):
                # TODO sync strategy
                print(f"Failed to append block at height {payload.start_height + i}, maybe due to mismatched prev_hash?")

    async def _mining_loop(self) -> None:
        """Mine only when there is at least one transaction in the mempool."""
        print("[mining] Started")

        while True:
            try:
                # Mining is CPU-bound, so run it in a worker thread.
                new_block = await asyncio.get_running_loop().run_in_executor(
                    None,
                    self.blockchain.mine_block,
                )
                if new_block is None:
                    print("Mining failed, skipping block broadcast")
                    continue
                self.broadcast_block(new_block)
                
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
                
            await asyncio.sleep(15)
                
    def extract_ith_block_from_payload(self, payload, i: int) -> Block | None:
        # payload.num_blocks: int
        # payload.blocks_data: bytes
        # Returns Block or None
        if i < 0 or i >= payload.num_blocks:
            return None

        data = payload.blocks_data
        offset = 0

        for idx in range(payload.num_blocks):
            # Fixed-size part: 32+32+8+8+8+32+2 = 122 bytes, plus fixed tx hash slots
            if len(data) - offset < 122 + MAX_TX_HASHES * 32:
                return None

            prev_hash = data[offset:offset + 32]
            offset += 32

            txs_hash = data[offset:offset + 32]
            offset += 32

            timestamp = int.from_bytes(data[offset:offset + 8], "big", signed=True)
            offset += 8

            difficulty = int.from_bytes(data[offset:offset + 8], "big", signed=True)
            offset += 8

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