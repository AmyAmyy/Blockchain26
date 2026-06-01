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
from constants import (
    REGISTRATION_COMMUNITY_ID,
    SERVER_PUBKEY_BYTES,
    BLOCKCHAIN_COMMUNITY_ID,
    GROUP_ID,
    MEMBER_COUNT,
    MY_MEMBER_ID,
    load_member_pubkeys,
)


class Lab3Community(Community):
    community_id = REGISTRATION_COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.member_id: int = MY_MEMBER_ID
        self.member_pubkeys: list[bytes] = load_member_pubkeys()
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

        self._server_peer: PeerType | None = None
        self._server_pubkey_bytes = SERVER_PUBKEY_BYTES

        self._registration_sent = False

        self.add_message_handler(RegisterResponse, self.on_register_response)

    def started(self) -> None:
        self.network.add_peer_observer(self)

    # ── helpers ─────────────────────────────────────────────────────────────
    
    def _registered(self) -> bool:
        return self.group_id is not None

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
        pk_hex = pk_bytes.hex()
        print(f"Found peer: {pk_hex[:40]}…")
        if pk_bytes == self._server_pubkey_bytes:
            print(f"Found server peer in lab3 community: {peer}")
            self._server_peer = peer

        elif pk_bytes in self.member_pubkeys:
            idx = self.member_pubkeys.index(pk_bytes)
            if self.member_peers[idx] is None:
                print(f"Found team member peer in lab3 community #{idx}: {peer}")
                self.member_peers[idx] = peer
                self._ready_peers.add(idx)
        
        if self._all_teammembers_known() and self._server_peer is not None:
            print("All team members and server discovered in lab3 community")
            if self.member_id == 0 and not self._registration_sent:
                self._registration_sent = True
                self._register_blockchain()
                
        
    def on_peer_removed(self, peer: PeerType) -> None:
        if self._server_peer is not None and peer == self._server_peer:
            print("⚠️  Server peer disconnected")
            self._server_peer = None
        if peer in self.member_peers:
            idx = self.member_peers.index(peer)
            print(f"⚠️  Team member peer #{idx} disconnected: {peer}")
            self.member_peers[idx] = None
            self._ready_peers.discard(idx)

    def _register_blockchain(self) -> None:
        assert self._server_peer is not None, "Server peer must be discovered before registering"
        assert self._all_teammembers_known(), "All team member peers must be discovered before registering"
        bundle = RegisterBlockchain(
            group_id = GROUP_ID,
            community_id = BLOCKCHAIN_COMMUNITY_ID
        )
        self.ez_send(self._server_peer, bundle)

    @lazy_wrapper(RegisterResponse)
    def on_register_response(self, peer: PeerType, payload: RegisterResponse) -> None:
        if peer.public_key.key_to_bin() != self._server_pubkey_bytes:
            print("Received RegisterResponse from unknown peer, ignoring")
            return
            
        if payload.success:
            print(f"Registered: {payload.message}")
        else:
            print(f"Registration failed: {payload.message}")