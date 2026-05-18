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

COMMUNITY_ID_HEX = "4c616233426c6f636b636861696e323032365057"
SERVER_PUBKEY_HEX = (
    "4c69624e61434c504b3ae3fc099fb56ca3b5e1de9a1c843387f2acdbb78b1bd4350ffde518068a0d246344b10d0d8c355fd0d76873e7d7f7838f3715e025af08f791324495e083331ce6"
)

KEY_FILES = ["first_key.txt", "second_key.txt", "third_key.txt"]
MEMBER_COUNT = 3
TOTAL_ROUNDS = 3

# 0, 1, or 2. Unique per team member, determines which pubkey we expect us to have
MY_MEMBER_ID = int(os.environ.get("MY_MEMBER_ID", "0"))


def _load_member_pubkeys() -> list[bytes]:
    """Load the 3 registered Lab-1 public keys from disk (hex-encoded)."""
    return [bytes.fromhex(open(p).read().strip()) for p in KEY_FILES]


class Lab2Community(Community):
    community_id = bytes.fromhex(COMMUNITY_ID_HEX)

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.member_id: int = MY_MEMBER_ID
        self.member_pubkeys: list[bytes] = _load_member_pubkeys()
        self.member_peers: list[PeerType | None] = [None] * MEMBER_COUNT
        self._ready_peers: set[int] = {self.member_id}

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

        # Protocol state
        self.group_id: str | None = None
        self.current_round: int = 1
        self._registration_sent = False
        # Per-round nonce + collected signatures (leader only)
        self._collected_sigs: dict[int, list[bytes | None]] = {}

        # Part 1
        self.add_message_handler(RegisterResponse, self.on_register_response)

        # Part 2
        self.add_message_handler(SubmitTransaction, self.on_submit_transaction)
        self.add_message_handler(GetChainHeight, self.on_chain_height)
        self.add_message_handler(GetBlock, self.on_get_block)

    def started(self) -> None:
        self.network.add_peer_observer(self)

    # ── helpers ─────────────────────────────────────────────────────────────

    # @staticmethod
    # def leader_of(round_n: int) -> int:
    #     """Round 1 → member 0, round 2 → member 1, round 3 → member 2."""
    #     return round_n - 1

    # def _i_am_leader(self) -> bool:
    #     return self.leader_of(self.current_round) == self.member_id
    
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

    # def _all_teammembers_known(self) -> bool:
    #     return all(p is not None for p in self.member_peers)

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

    # ── Part 1 ─────────────────────────────────────────────
    def _register_group(self) -> None:
        assert self._server_peer is not None, "Server peer must be discovered before registering"
        bundle = RegisterBlockchain(
            member1_key=self.member_pubkeys[0],
            member2_key=self.member_pubkeys[1],
            member3_key=self.member_pubkeys[2],
        )
        self.ez_send(self._server_peer, bundle)

    @lazy_wrapper(RegisterResponse)
    def on_register_response(self, peer: PeerType, payload: RegisterResponse) -> None:
        return

    # ── Part 2 ─────────────────────────────────────────────
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
