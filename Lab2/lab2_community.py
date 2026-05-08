import os
import asyncio
from ipv8.community import Community, CommunitySettings
from ipv8.peer import Peer as PeerType
from ipv8.lazy_community import lazy_wrapper

from message_payloads import RegisterPayload, ResponsePayload, ChallengeRequestPayload, ChallengeResponsePayload, SubmissionPayload, RoundResultPayload
from ipv8.keyvault.crypto import default_eccrypto

COMMUNITY_ID_HEX = "4c61623247726f75705369676e696e6732303236"
SERVER_PUBKEY_HEX = (
    "4c69624e61434c504b3a82e33614a342774e084af80835838d6dbdb64a537d3ddb6c1d82011a7f101553cda40cf5fa0e0fc23abd0a9c4f81322282c5b34566f6b8401f5f683031e60c96"
)

PERSONAL_COMMUNITY_ID_HEX = b'v\x16p\xca\x81L\n\xa2IjX\x84\x0b\x7f\xe7\x83\xc0\xb4\xd0p'

MEMBER_COUNT = 3
KEY_FILE1 = "first_key.txt"
KEY_FILE2 = "second_key.txt"
KEY_FILE3 = "third_key.txt"

member_pubkeys: list[bytes] = []

MY_MEMBER_ID = 0

# ─── IPv8 Community ──────────────────────────

class Lab2Community(Community):
    community_id = bytes.fromhex(COMMUNITY_ID_HEX)
 
    global member_pubkeys
    # keys = [load_or_create_key(k) for k in [KEY_FILE1, KEY_FILE2, KEY_FILE3]]
    # _member_pubkeys = [k.pub().key_to_bin() for k in keys]
    member_pubkeys = [
        bytes.fromhex(open(KEY_FILE1).read().strip()),
        bytes.fromhex(open(KEY_FILE2).read().strip()),
        bytes.fromhex(open(KEY_FILE3).read().strip()),
    ]

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.member_id = MY_MEMBER_ID
        self.member_pubkeys = member_pubkeys
        self.member_peers: list[PeerType] = [None] * MEMBER_COUNT

        self.add_message_handler(ResponsePayload, self.on_response)
        self.add_message_handler(ChallengeResponsePayload, self.on_challenge_response)
        self.add_message_handler(RoundResultPayload, self.on_round_result)
        self._server_peer: PeerType | None = None
        self.registered_group = False
        self._done = asyncio.Event()
        self._challenge_counter = 0
        
        # Pre-decode the server public key for comparison
        self._server_pubkey_bytes = bytes.fromhex(SERVER_PUBKEY_HEX)
        
 
    def started(self) -> None:
        self.network.add_peer_observer(self)

    # ── peer discovery ──
 
    def on_peer_added(self, peer: PeerType) -> None:
        print("Peer discovered:", peer)
        pk_bytes = peer.public_key.key_to_bin()
        if pk_bytes == self._server_pubkey_bytes:
            print(f"🔗  Found server peer: {peer}")
            self._server_peer = peer
            if not self.registered_group:
                self.registered_group = True
                asyncio.ensure_future(self.register_group())
            else:
                asyncio.ensure_future(self.start_challenge())
        
        elif pk_bytes in self.member_pubkeys:
            print(f"👥  Found team member peer: {peer}")
            peer_index = self.member_pubkeys.index(pk_bytes)
            self.member_peers[peer_index] = peer

        # if self._server_peer:
        #     print(f"Found server peer.")
        #     self.server_peer = server
        #     self.send_submission(email, github_url, nonce)
        #     return
            
        # if self._server_peer and all(self.member_peers):
        #     print("All peers discovered, ready for challenge")
            # if self._challenge_counter == 0 and self.member_id == 0:
            #     asyncio.ensure_future(self._start_challenge())
 
    def on_peer_removed(self, peer: PeerType) -> None:
        if self._server_peer and peer == self._server_peer:
            print("⚠️  Server peer disconnected")
            self._server_peer = None
 
    async def register_group(self) -> None:
        print(f"\n👥  Registering group with server…")
        payload = RegisterPayload(
            member1_key=self.member_pubkeys[0],
            member2_key=self.member_pubkeys[1],
            member3_key=self.member_pubkeys[2],
        )

        print(f"\n📤  Sending registration to server…")
        self.ez_send(self._server_peer, payload) # Part 1
 
    async def start_challenge(self) -> None:
        print(f"\n🚀  Starting challenge round ({self._challenge_counter})")

        challengeRequestPayload = ChallengeRequestPayload(group_id=open("group_id.txt").read().strip())        
        print(f"\n📤  Sending challenge to server…")
        self.ez_send(self._server_peer, challengeRequestPayload) # Part 2
 
    @lazy_wrapper(ResponsePayload)
    def on_response(self, peer: PeerType, payload: ResponsePayload) -> None:
        if (peer.public_key.key_to_bin() != self._server_pubkey_bytes):
            print(f"⚠️  Ignoring response from unknown peer {peer}")
            return
 
        status = "✅  ACCEPTED" if payload.success else "❌  REJECTED"
        print(f"\n{status}")
        print(f"   Message: {payload.message} (Group ID: {payload.group_id})")
        self._done.set()
    
    @lazy_wrapper(ChallengeResponsePayload)
    def on_challenge_response(self, peer: PeerType, payload: ChallengeResponsePayload) -> None:
        if (peer.public_key.key_to_bin() != self._server_pubkey_bytes):
            print(f"⚠️  Ignoring response from unknown peer {peer}")
            return
 
        nonce = payload.nonce
        round_number = payload.round_number
        deadline = payload.deadline
        
        print(f"\n⏳  Challenge received for round {round_number} with deadline {deadline} with nonce {nonce.hex()}")
        
        self._done.set()
    
    @lazy_wrapper(RoundResultPayload)
    def on_round_result(self, peer, payload):
        print(f"Round result: success={payload.success}, round={payload.round_number}, msg={payload.message}")

    async def wait_for_response(self, timeout: float = 120.0) -> None:
        try:
            await asyncio.wait_for(self._done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print("\n⏰  Timed out waiting for server response.")
            print("    Check that IPv8 peer discovery is working and your")
            print("    packet is being signed (ez_send was used).") 
    
def load_or_create_key(path: str):
    if os.path.exists(path):
        print(f"🔑  Loading existing key from {path}")
        with open(path, "rb") as f:
            return default_eccrypto.key_from_private_bin(f.read())