import os
import asyncio
from ipv8.community import Community, CommunitySettings
from ipv8.peer import Peer as PeerType
from ipv8.lazy_community import lazy_wrapper

from message_payloads import (
    RegisterBlockchain,
    RegisterResponse,
    GetChainHeight,
    ChainHeightResponse,
    GetBlock,
    BlockResponse,
    SubmitTransaction,
    SubmitTransactionResponse
)

COMMUNITY_ID = '\x01\xb6\xf0}H\xc6R\xc9H\x1a\xd6\x11H\xf6{G%i\xf3i'
SERVER_PUBKEY_HEX = (
    "4c69624e61434c504b3ae3fc099fb56ca3b5e1de9a1c843387f2acdbb78b1bd4350ffde518068a0d246344b10d0d8c355fd0d76873e7d7f7838f3715e025af08f791324495e083331ce6"
)

KEY_FILES = ["first_key.txt", "second_key.txt", "third_key.txt"]
MEMBER_COUNT = 3

# 0, 1, or 2. Unique per team member, determines which pubkey we expect us to have
MY_MEMBER_ID = int(os.environ.get("MY_MEMBER_ID", "0"))

def _load_member_pubkeys() -> list[bytes]:
    """Load the 3 registered Lab-1 public keys from disk (hex-encoded)."""
    return [bytes.fromhex(open(p).read().strip()) for p in KEY_FILES]

class BlockchainCommunity(Community):
    community_id = COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.member_id: int = MY_MEMBER_ID
        self.member_pubkeys: list[bytes] = _load_member_pubkeys()
        self.member_peers: list[PeerType | None] = [None] * MEMBER_COUNT

        self.group_id = "206290bb8cc8016f"

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

        self._server_pubkey_bytes = bytes.fromhex(SERVER_PUBKEY_HEX)
        self._server_peer: PeerType | None = None

        self.add_message_handler(SubmitTransaction, self.on_submit_transaction)
        self.add_message_handler(GetChainHeight, self.on_chain_height)
        self.add_message_handler(GetBlock, self.on_get_block)

    def started(self) -> None:
        self.network.add_peer_observer(self)

    # ── helpers ─────────────────────────────────────────────────────────────
    
    def _registered(self) -> bool:
        return self.group_id is not None

    # def _sign(self, nonce: bytes) -> bytes:
    #     """Ed25519 sign the raw nonce with our IPv8 key."""
    #     return self.my_peer.key.signature(nonce)

    def _send_to_member(self, member_idx: int, payload) -> None:
        peer = self.member_peers[member_idx]
        if peer is None:
            # print(f"⚠️  Cannot send to member {member_idx}: peer not yet discovered")
            return
        self.ez_send(peer, payload)

    def _all_teammembers_known(self) -> bool:
        return all(p is not None for p in self.member_peers)

    # ── peer discovery ──────────────────────────────────────────────────────
    def on_peer_added(self, peer: PeerType) -> None:
        pk_bytes = peer.public_key.key_to_bin()
        if pk_bytes == self._server_pubkey_bytes:
            # print(f"Found server peer: {peer}")
            self._server_peer = peer

        elif pk_bytes in self.member_pubkeys:
            idx = self.member_pubkeys.index(pk_bytes)
            if self.member_peers[idx] is None:
                # print(f"Found team member peer #{idx}: {peer}")
                self.member_peers[idx] = peer
                self._ready_peers.add(idx)
        
        if self._all_teammembers_known() and self._server_peer is not None:
            # print("All team members and server discovered")
            if self.member_id == 0 and not self._registration_sent:
                self._registration_sent = True
                asyncio.ensure_future(self._register_group())
                
        
    def on_peer_removed(self, peer: PeerType) -> None:
        if self._server_peer is not None and peer == self._server_peer:
            # print("⚠️  Server peer disconnected")
            self._server_peer = None
        if peer in self.member_peers:
            idx = self.member_peers.index(peer)
            # print(f"⚠️  Team member peer #{idx} disconnected: {peer}")
            self.member_peers[idx] = None
            self._ready_peers.discard(idx)

    @lazy_wrapper(SubmitTransaction)
    def on_submit_transaction(self, peer: PeerType, payload: SubmitTransaction) -> None:
        return
    
    def _submit_transaction_response(self) -> None:
        bundle = SubmitTransactionResponse(
            # TODO
        )
        self.ez_send(self._server_peer, bundle)
    
    @lazy_wrapper(GetChainHeight)
    def on_chain_height(self, peer: PeerType, payload: GetChainHeight) -> None:
        return

    def _chain_height_response(self) -> None:
        bundle = ChainHeightResponse(
            # TODO
        )
        self.ez_send(self._server_peer, bundle)

    @lazy_wrapper(GetBlock)
    def on_get_block(self, peer: PeerType, payload: GetBlock) -> None:
        return
    
    def _block_response(self) -> None:
        bundle = BlockResponse(
            # TODO
        )
        self.ez_send(self._server_peer, bundle)
