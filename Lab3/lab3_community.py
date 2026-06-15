from ipv8.community import Community, CommunitySettings
from ipv8.peer import Peer as PeerType
from ipv8.lazy_community import lazy_wrapper

from message_payloads import (
    RegisterBlockchain,
    RegisterResponse,
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

        # My IPv8 key must match the pubkey at MY_MEMBER_ID,
        my_pk = self.my_peer.public_key.key_to_bin()
        expected = self.member_pubkeys[self.member_id]
        if my_pk != expected:
            raise RuntimeError(
                f"MY_MEMBER_ID={self.member_id} but my_peer pubkey does not match "
                f"the expected pubkey for that member ID."
            )
        # I already know my own peer object.
        self.member_peers[self.member_id] = self.my_peer

        self.server_peer: PeerType | None = None
        self.server_pubkey_bytes = SERVER_PUBKEY_BYTES

        self.registration_sent = False

        self.add_message_handler(RegisterResponse, self.on_register_response)

    def started(self) -> None:
        self.network.add_peer_observer(self)

    def registered(self) -> bool:
        return self.group_id is not None

    def send_to_member(self, member_idx: int, payload) -> None:
        peer = self.member_peers[member_idx]
        if peer is None:
            return
        self.ez_send(peer, payload)

    def all_teammembers_known(self) -> bool:
        return all(p is not None for p in self.member_peers)

    def on_peer_added(self, peer: PeerType) -> None:
        pk_bytes = peer.public_key.key_to_bin()
        if pk_bytes == self.server_pubkey_bytes:
            print(f"[LAB3COM] Found server peer in: {peer}")
            self.server_peer = peer

        elif pk_bytes in self.member_pubkeys:
            idx = self.member_pubkeys.index(pk_bytes)
            if self.member_peers[idx] is None:
                print(f"[LAB3COM] Found team member peer #{idx}: {peer}")
                self.member_peers[idx] = peer
        
        if self.all_teammembers_known() and self.server_peer is not None:
            print("[LAB3COM] All team members and server discovered in lab3 community")
            if self.member_id == 0 and not self.registration_sent:
                self.registration_sent = True
                self.register_blockchain()
                
        
    def on_peer_removed(self, peer: PeerType) -> None:
        if self.server_peer is not None and peer == self.server_peer:
            print("[LAB3COM] Server peer disconnected")
            self.server_peer = None
        if peer in self.member_peers:
            idx = self.member_peers.index(peer)
            print(f"[LAB3COM] Team member peer #{idx} disconnected: {peer}")
            self.member_peers[idx] = None

    def register_blockchain(self) -> None:
        if not self.server_peer or not self.all_teammembers_known():
            print("[LAB3COM] Cannot register blockchain yet; waiting for all peers to be discovered")
            return

        print("[LAB3COM] Registering blockchain with server...")
        bundle = RegisterBlockchain(
            group_id = GROUP_ID,
            community_id = BLOCKCHAIN_COMMUNITY_ID
        )
        self.ez_send(self.server_peer, bundle)

    @lazy_wrapper(RegisterResponse)
    def on_register_response(self, peer: PeerType, payload: RegisterResponse) -> None:
        if peer.public_key.key_to_bin() != self.server_pubkey_bytes:
            return
            
        if payload.success:
            print(f"[LAB3COM] Registered: {payload.message}")
        else:
            print(f"[LAB3COM] Registration failed: {payload.message}")