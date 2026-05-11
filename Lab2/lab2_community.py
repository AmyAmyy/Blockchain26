import os
import asyncio
from ipv8.community import Community, CommunitySettings
from ipv8.peer import Peer as PeerType
from ipv8.lazy_community import lazy_wrapper

from message_payloads import (
    RegisterPayload,
    ResponseRegisterPayload,
    ChallengeRequestPayload,
    ChallengeResponsePayload,
    SubmissionPayload,
    RoundResultPayload,
    GroupIdPayload,
    NoncePayload,
    SignaturePayload,
)

COMMUNITY_ID_HEX = "4c61623247726f75705369676e696e6732303236"
SERVER_PUBKEY_HEX = (
    "4c69624e61434c504b3a82e33614a342774e084af80835838d6dbdb64a537d3ddb6c1d82011a7f101553cda40cf5fa0e0fc23abd0a9c4f81322282c5b34566f6b8401f5f683031e60c96"
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

        # Server-defined messages
        self.add_message_handler(ResponseRegisterPayload, self.on_response)
        self.add_message_handler(ChallengeResponsePayload, self.on_challenge_response)
        self.add_message_handler(RoundResultPayload, self.on_round_result)

        # Peer-to-peer protocol messages
        self.add_message_handler(GroupIdPayload, self.on_group_id)
        self.add_message_handler(NoncePayload, self.on_nonce)
        self.add_message_handler(SignaturePayload, self.on_signature)

    def started(self) -> None:
        self.network.add_peer_observer(self)

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def leader_of(round_n: int) -> int:
        """Round 1 → member 0, round 2 → member 1, round 3 → member 2."""
        return round_n - 1

    def _i_am_leader(self) -> bool:
        return self.leader_of(self.current_round) == self.member_id
    
    def _registered(self) -> bool:
        return self.group_id is not None

    def _sign(self, nonce: bytes) -> bytes:
        """Ed25519 sign the raw nonce with our IPv8 key."""
        return self.my_peer.key.signature(nonce)

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

    # ── bootstrap: registration ─────────────────────────────────────────────

    async def _register_group(self) -> None:
        # print("Registering group with server...")
        payload = RegisterPayload(
            member1_key=self.member_pubkeys[0],
            member2_key=self.member_pubkeys[1],
            member3_key=self.member_pubkeys[2],
        )
        self.ez_send(self._server_peer, payload)

    @lazy_wrapper(ResponseRegisterPayload)
    def on_response(self, peer: PeerType, payload: ResponseRegisterPayload) -> None:
        # print(f"Received response from peer {peer}")
        if peer.public_key.key_to_bin() != self._server_pubkey_bytes:
            # print(f"⚠️  Ignoring ResponseRegisterPayload from unknown peer {peer}")
            return
        if not payload.success:
            # print(f"❌  Registration failed: {payload.message}")
            return
        # print(f"✅  Registered: {payload.message} (group_id={payload.group_id})")
        self.group_id = payload.group_id
        self._broadcast_group_id()
        asyncio.ensure_future(self._start_round())

    def _broadcast_group_id(self) -> None:
        """Member 0 only: tell teammembers the group_id."""
        assert self.member_id == 0, "Only member 0 should broadcast the group_id"
        payload = GroupIdPayload(group_id=self.group_id)
        for idx in (1, 2):
            if self.member_peers[idx] is not None:
                self._send_to_member(idx, payload)

    @lazy_wrapper(GroupIdPayload)
    def on_group_id(self, peer: PeerType, payload: GroupIdPayload) -> None:
        # Only accept from member 0.
        sender_pk = peer.public_key.key_to_bin()
        if sender_pk != self.member_pubkeys[0]:
            # print(f"⚠️  Ignoring GroupIdPayload from non-member-0 peer")
            return
        if self.group_id is None:
            self.group_id = payload.group_id
            # print(f"📥  Received group_id from member 0: {self.group_id}")

    # ── round driver ────────────────────────────────────────────────────────

    async def _start_round(self) -> None:
        assert self._i_am_leader(), "Only the round leader requests the challenge"
        self._collected_sigs[self.current_round] = [None, None, None]
        # print(f"\n🚀  [round {self.current_round}] (leader={self.member_id}) requesting challenge")
        self.ez_send(self._server_peer, ChallengeRequestPayload(group_id=self.group_id))
        
    def _send_broadcast_nonce(self, round_number: int, nonce: bytes) -> None:
        """Boadcasts the nonce to the other members."""
        payload = NoncePayload(round_number=round_number, nonce=nonce)
        for idx in range(MEMBER_COUNT):
            if idx != self.member_id:
                self._send_to_member(idx, payload)

    @lazy_wrapper(ChallengeResponsePayload)
    def on_challenge_response(self, peer: PeerType, payload: ChallengeResponsePayload) -> None:
        if peer.public_key.key_to_bin() != self._server_pubkey_bytes:
            # print(f"⚠️  Ignoring ChallengeResponsePayload from unknown peer {peer}")
            return
        round_number = payload.round_number
        nonce = payload.nonce
        if not self._i_am_leader():
            # print(f"⚠️  Got ChallengeResponse for round {round_number} but I am not its leader")
            return
        # Broadcast nonce to the other two members in parallel.
        self._send_broadcast_nonce(round_number, nonce)
        # Sign locally and store our own slot.
        my_sig = self._sign(nonce)
        self._collected_sigs[round_number][self.member_id] = my_sig
        

    @lazy_wrapper(NoncePayload)
    def on_nonce(self, peer: PeerType, payload: NoncePayload) -> None:
        round_number = payload.round_number
        sig = self._sign(payload.nonce)
        leader_idx = self.leader_of(round_number)
        sig_payload = SignaturePayload(
            round_number=round_number,
            member_index=self.member_id,
            signature=sig,
        )
        self._send_to_member(leader_idx, sig_payload)

    @lazy_wrapper(SignaturePayload)
    def on_signature(self, peer: PeerType, payload: SignaturePayload) -> None:
        round_number = payload.round_number
        idx = payload.member_index
        # Validate sender pubkey matches the claimed member_index.
        sender_pk = peer.public_key.key_to_bin()
        if idx < 0 or idx >= MEMBER_COUNT or sender_pk != self.member_pubkeys[idx]:
            # print(f"⚠️  Ignoring SignaturePayload: sender does not match member_index={idx}")
            return
        if not self._i_am_leader():
            # print(f"⚠️  Got SignaturePayload for round {round_number} but I am not its leader")
            return
        self._collected_sigs[round_number][idx] = payload.signature
        if self._collected_sigs[round_number].count(None) == 0:
            self._submit_round()

    def _submit_round(self) -> None:
        round_number = self.current_round
        sigs = self._collected_sigs[round_number]
        # print(f"📤  [round {round_number}] all 3 sigs collected, submitting bundle ")
        bundle = SubmissionPayload(
            group_id=self.group_id,
            round_number=round_number,
            sig1=sigs[0],
            sig2=sigs[1],
            sig3=sigs[2],
        )
        self.ez_send(self._server_peer, bundle)

    @lazy_wrapper(RoundResultPayload)
    def on_round_result(self, peer: PeerType, payload: RoundResultPayload) -> None:
        sender_pk = peer.public_key.key_to_bin()
        is_from_server = (sender_pk == self._server_pubkey_bytes)
        is_from_teammate = sender_pk in self.member_pubkeys
        
        if not (is_from_server or is_from_teammate):
            # print(f"⚠️  Ignoring RoundResultPayload from unknown peer {peer}")
            return
        
        round_number = payload.round_number
        if not payload.success:
            # print(f"❌  Round {round_number} failed: {payload.message}")
            return

        if is_from_server:
            # print(f"✅  Round {round_number} successful: {payload.message}")
            
            # Broadcast the result to other members
            for idx in range(MEMBER_COUNT):
                if idx != self.member_id:
                    self._send_to_member(idx, payload)
        
        # Auto-advance if I'm the next leader
        next_round = round_number + 1
        if next_round <= TOTAL_ROUNDS and self.leader_of(next_round) == self.member_id:
            self.current_round = next_round
            asyncio.ensure_future(self._start_round())