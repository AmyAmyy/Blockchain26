import asyncio
import random
import time
from ipv8.community import Community, CommunitySettings
from ipv8.peer import Peer as PeerType
from ipv8.lazy_community import lazy_wrapper
from constants import MAX_SEARCH_DEPTH

from helpers import extract_ith_block_from_payload
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
    PARTITION_TEST_ENABLED,
    PARTITION_START_AFTER_SECONDS,
    PARTITION_DURATION_SECONDS,
    MAX_SLEEP_MINING_LOOP,
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
        self.group_id = GROUP_ID

        self.blockchain = Blockchain()
        self.mining_task: asyncio.Task | None = None
        self.polling_task: asyncio.Task | None = None

        self.started_at: float = time.monotonic()

        # My IPv8 key must match the pubkey at MY_MEMBER_ID
        my_pk = self.my_peer.public_key.key_to_bin()
        expected = self.member_pubkeys[self.member_id]
        if my_pk != expected:
            raise RuntimeError(
                f"MY_MEMBER_ID={self.member_id} but my_peer pubkey does not match "
                f"the expected pubkey for that member ID."
            )
        # I already know my own peer object.
        self.member_peers[self.member_id] = self.my_peer

        self.server_pubkey_bytes = SERVER_PUBKEY_BYTES
        self.server_peer: PeerType | None = None

        self.add_message_handler(SubmitTransaction, self.on_submit_transaction)
        self.add_message_handler(GetChainHeight, self.on_chain_height)
        self.add_message_handler(GetBlock, self.on_get_block)
        self.add_message_handler(BlockResponse, self.on_block_response)
        self.add_message_handler(GetMultipleBlocks, self.on_get_multiple_blocks)
        self.add_message_handler(MultipleBlocksResponse, self.on_multiple_blocks_response)
        self.add_message_handler(ChainHeightResponse, self.on_chain_height_response)

    def started(self) -> None:
        self.started_at = time.monotonic()
        self.network.add_peer_observer(self)
        if self.polling_task is None:
            self.polling_task = asyncio.create_task(self._polling_loop())

    def partition_active(self) -> bool:
        if not PARTITION_TEST_ENABLED:
            return False
        elapsed = time.monotonic() - self.started_at
        return PARTITION_START_AFTER_SECONDS <= elapsed < (PARTITION_START_AFTER_SECONDS + PARTITION_DURATION_SECONDS)

    def can_exchange_with_peer(self, peer: PeerType) -> bool:
        '''Return True if peer is the server or member peer in our partition, otherwise False.'''
        # Peer is the server, always keep the communication
        if self.server_peer is not None and peer == self.server_peer:
            return True
        
        if peer in self.member_peers:
            if self.partition_active():
                print("[PARTITION] Dropping outbound message across partition to member")
                return False
            else:
                return True

        # Unknown peer
        return False

    def safe_send(self, peer: PeerType, payload: object) -> None:
        if peer is None or peer == self.my_peer:
            return
        
        if not self.can_exchange_with_peer(peer):
            return
        
        self.ez_send(peer, payload)

    def all_teammembers_known(self) -> bool:
        return all(p is not None for p in self.member_peers)
    
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
            self.safe_send(peer, bundle)
    
    def on_peer_added(self, peer: PeerType) -> None:
        pk_bytes = peer.public_key.key_to_bin()
        if pk_bytes == self.server_pubkey_bytes:
            print(f"[DISCOVERY] Found in blockchain community server peer: {peer}")
            self.server_peer = peer

        elif pk_bytes in self.member_pubkeys:
            idx = self.member_pubkeys.index(pk_bytes)
            if self.member_peers[idx] is None:
                print(f"[DISCOVERY] Found in blockchain community team member peer #{idx}: {peer}")
                self.member_peers[idx] = peer
        
        if self.all_teammembers_known() and self.server_peer is not None and self.mining_task is None:
            self.mining_task = asyncio.create_task(self._mining_loop())
            print(f"[DISCOVERY] All team members and server discovered")
        
    def on_peer_removed(self, peer: PeerType) -> None:
        if self.server_peer is not None and peer == self.server_peer:
            print(f"[DISCOVERY] Server peer disconnected: {peer}")
            self.server_peer = None

        if peer in self.member_peers:
            idx = self.member_peers.index(peer)
            print(f"[DISCOVERY] Team member peer #{idx} disconnected: {peer}")
            self.member_peers[idx] = None
    
    @lazy_wrapper(SubmitTransaction)
    def on_submit_transaction(self, peer: PeerType, payload: SubmitTransaction) -> None:
        if not self.can_exchange_with_peer(peer):
            return

        print(f"[TRANSACTION] Received transaction from peer {peer}")

        transaction = Transaction(
            sender_key = payload.sender_key,
            data = payload.data,
            timestamp = payload.timestamp,
            signature = payload.signature,
        )

        if not transaction.verify_signature():
            print(f"[TRANSACTION] Received transaction with invalid signature: {transaction.tx_hash}")
            bundle = SubmitTransactionResponse(
                success = False,
                tx_hash = transaction.tx_hash,
                message = "Invalid transaction signature"
            )
            self.safe_send(peer, bundle)
            return
        
        if not self.blockchain.add_transaction(transaction):
            print(f"[TRANSACTION] Failed to add transaction to mempool, duplicate tx found: {transaction.tx_hash}")
            bundle = SubmitTransactionResponse(
                success = False,
                tx_hash = transaction.tx_hash,
                message = "Failed to add transaction"
            )
            self.safe_send(peer, bundle)
            return
        
        print(f"[TRANSACTION] Added transaction to mempool: {transaction.tx_hash}, mempool size is now {len(self.blockchain.mempool)}")
        bundle = SubmitTransactionResponse(
            success = True,
            tx_hash = transaction.tx_hash,
            message = "Transaction accepted"
        )
        self.safe_send(peer, bundle)
        
    
    @lazy_wrapper(GetChainHeight)
    def on_chain_height(self, peer: PeerType, payload: GetChainHeight) -> None:        
        if not self.can_exchange_with_peer(peer):
            return
        
        height = self.blockchain.get_chain_height()
        tip_hash = self.blockchain.get_block(height).block_hash
        bundle = ChainHeightResponse(
            request_id = payload.request_id,
            height = height,
            tip_hash = tip_hash,
        )
        self.safe_send(peer, bundle)
        
    @lazy_wrapper(ChainHeightResponse)
    def on_chain_height_response(self, peer: PeerType, payload: ChainHeightResponse) -> None:
        if not self.can_exchange_with_peer(peer):
            return

        local_height = self.blockchain.get_chain_height()
        local_tip_hash = self.blockchain.get_block(local_height).block_hash
        print(f"[poll] ChainHeightResponse from {peer}: height={payload.height}")

        if payload.height > local_height or (payload.height == local_height and payload.tip_hash != local_tip_hash):
            start_height = max(0, local_height - MAX_SEARCH_DEPTH)
            print(f"[poll] Remote chain is newer or diverged; requesting blocks from {peer} starting at {start_height}")
            self.safe_send(peer, GetMultipleBlocks(start_height=start_height))

    @lazy_wrapper(GetBlock)
    def on_get_block(self, peer: PeerType, payload: GetBlock) -> None:       
        if not self.can_exchange_with_peer(peer):
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
        self.safe_send(peer, bundle)
    
    @lazy_wrapper(BlockResponse)
    def on_block_response(self, peer: PeerType, payload: BlockResponse) -> None:
        print(f"Received block")
        
        if not self.can_exchange_with_peer(peer):
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
            self.safe_send(peer, bundle)
            return
        
        if not self.blockchain.append_block(block):
            # Competing branch: only reorg if their chain is strictly longer
            if payload.height > self.blockchain.get_chain_height():
                print(f"Competing branch detected at height {payload.height}, fetching overlap window")
                self.safe_send(peer, GetMultipleBlocks(
                    start_height=max(0, self.blockchain.get_chain_height() - MAX_SEARCH_DEPTH)
                ))
            else:
                print(f"Failed to append block at height {payload.height}, ignoring")

        print(f"Added block at height {payload.height} to the chain")
        print(f"Chain height is now {self.blockchain.get_chain_height()}")
    
    @lazy_wrapper(GetMultipleBlocks)
    def on_get_multiple_blocks(self, peer: PeerType, payload: GetMultipleBlocks) -> None:
        print(f"Received request for multiple blocks starting at height {payload.start_height}")
        
        if not self.can_exchange_with_peer(peer):
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
            blocks_data += block.difficulty.to_bytes(4, "big", signed=False)
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
        self.safe_send(peer, bundle)

    @lazy_wrapper(MultipleBlocksResponse)
    def on_multiple_blocks_response(self, peer: PeerType, payload: MultipleBlocksResponse) -> None:
        print(f"Received multiple blocks")
        
        if not self.can_exchange_with_peer(peer):
            return

        if payload.start_height - 1 > self.blockchain.get_chain_height():
            print(f"Missing blocks, cannot add block at height {payload.start_height}")
            return
        
        # Build list of blocks from payload and verify them
        blocks: list[Block] = []
        for i in range(payload.num_blocks):
            block = extract_ith_block_from_payload(payload, i)
            if block is None:
                print(f"Failed to parse block index {i} from MultipleBlocksResponse")
                return

            if not block.verify_block():
                print(f"NOT GOOD, block wrong")
                return
            
            blocks.append(block)

        # Try to append blocks
        their_height = payload.start_height + payload.num_blocks - 1
        for idx, block in enumerate(blocks):
            current_height = payload.start_height + idx

            if current_height <= self.blockchain.get_chain_height():
                # Overlap with local chain: compare hashes to detect divergence.
                local_block = self.blockchain.get_block(current_height)
                if local_block is None:
                    print(f"Missing local block at height {current_height} during overlap check")
                    return
                if local_block.block_hash != block.block_hash:
                    our_height = self.blockchain.get_chain_height()
                    if their_height > our_height:
                        print(f"Detected stronger fork at overlap height {current_height}, resolving")
                        self._fork_resolution(peer, their_height, blocks[idx:], current_height)
                    else:
                        print(f"Detected competing fork at overlap height {current_height}, keeping local chain")
                    return
                continue
            
            if self.blockchain.append_block(block):
                print(f"Appended block at height {current_height} to the chain")
            else:
                # fork resolution
                self._fork_resolution(peer, their_height, blocks[idx:], current_height)
                return

    def _fork_resolution(self, peer: PeerType, their_height: int, branch: list[Block], branch_start_height: int) -> None:
        # Fork resolution: if any blocks didn't append cleanly, find common ancestor
        if their_height > self.blockchain.get_chain_height():
            ancestor_height = self.blockchain.find_common_ancestor(branch)
            if ancestor_height is None:
                if branch_start_height == 0 or their_height - branch_start_height >= MAX_SEARCH_DEPTH:
                    print("[reorg] No common ancestor found, cannot resolve fork")
                    return
                fetch_start = max(0, their_height - MAX_SEARCH_DEPTH)
                print(f"[reorg] Ancestor not found; requesting earlier blocks from {fetch_start}")
                self.safe_send(peer, GetMultipleBlocks(start_height=fetch_start))
                return
            
            fork_start_index = ancestor_height + 1 - branch_start_height
            if not self.blockchain.switch_to_fork(ancestor_height, branch[max(0, fork_start_index):]):
                print("[reorg] Failed to switch to fork")
                return
            print(f"Chain height is now {self.blockchain.get_chain_height()}")

    async def _polling_loop(self) -> None:
        print("[poll] Started chain height polling")
        while True:
            peers = [p for p in self.member_peers if p is not None and p != self.my_peer]
            if self.server_peer is not None:
                peers.append(self.server_peer)

            if peers:
                peer = random.choice(peers)
                request_id = time.time_ns()
                print(f"[poll] Requesting chain height from {peer} (request_id={request_id})")
                self.safe_send(peer, GetChainHeight(request_id=request_id))

            await asyncio.sleep(5)

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
                
            await asyncio.sleep(random.uniform(1, MAX_SLEEP_MINING_LOOP))