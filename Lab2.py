import asyncio
import hashlib
import multiprocessing
import os
import struct
import time
from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs, BootstrapperDefinition, Bootstrapper
from ipv8.keyvault.crypto import default_eccrypto
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.payload_dataclass import VariablePayload, vp_compile
from ipv8.peer import Peer as PeerType
from ipv8_service import IPv8

COMMUNITY_ID_HEX = "4c61623247726f75705369676e696e6732303236"
SERVER_PUBKEY_HEX = (
    "4c69624e61434c504b3a82e33614a342774e084af80835838d6dbdb64a537d3ddb6c1d82011a7f101553cda40cf5fa0e0fc23abd0a9c4f81322282c5b34566f6b8401f5f683031e60c96"
)

KEY_FILE1 = "my_key.pem"
KEY_FILE2 = "second_key.pem"
KEY_FILE3 = "third_key.pem"



_member_pubkeys: list[bytes] = []
# ─── Message payloads ────────────────────────
 
class RegisterPayload(VariablePayload):
    msg_id = 1
    format_list = ["varlenH", "varlenH", "varlenH"]
    names = ["member1_key", "member2_key", "member3_key"]
 
 
class ResponsePayload(VariablePayload):
    msg_id = 2
    format_list = ["?", "varlenHutf8", "varlenHutf8"]
    names = ["success", "group_id", "message"]
 
 
# Compile for faster (de)serialisation
RegisterPayload = vp_compile(RegisterPayload)
ResponsePayload   = vp_compile(ResponsePayload)
 
 
 
# ─── IPv8 Community ──────────────────────────
 
class Lab2Community(Community):
    community_id = bytes.fromhex(COMMUNITY_ID_HEX)
 
    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self._member_pubkeys = _member_pubkeys

        self.add_message_handler(ResponsePayload, self.on_response)
        self._server_peer: PeerType | None = None
        self._submitted = False
        self._done = asyncio.Event()
 
        # Pre-decode the server public key for comparison
        self._server_pubkey_bytes = bytes.fromhex(SERVER_PUBKEY_HEX)
 
    def started(self) -> None:
        self.network.add_peer_observer(self)
    # def started(self) -> None:
    #     async def debug_peers():
    #         peers = self.get_peers()
    #         print(f"👀 Peers seen: {len(peers)}")
    #         for p in peers:
    #             print("   ", p)

    #     self.register_task("debug_peers", debug_peers, interval=5.0, delay=0) 

    # ── peer discovery ──
 
    def on_peer_added(self, peer: PeerType) -> None:
        print("Peer discovered:", peer)
        pk_bytes = peer.public_key.key_to_bin()
        if pk_bytes == self._server_pubkey_bytes:
            print(f"🔗  Found server peer: {peer}")
            self._server_peer = peer
            if not self._submitted:
                self._submitted = True
                asyncio.ensure_future(self._submit())
                
 
    def on_peer_removed(self, peer: PeerType) -> None:
        if self._server_peer and peer == self._server_peer:
            print("⚠️  Server peer disconnected")
            self._server_peer = None
 
    # ── submission ──
 
    async def _submit(self) -> None:
        payload = RegisterPayload(
            member1_key=self._member_pubkeys[0],
            member2_key=self._member_pubkeys[1],
            member3_key=self._member_pubkeys[2],
        )
        print(f"\n📤  Sending submission to server…")
        self.ez_send(self._server_peer, payload)
 
    # ── response handler ──
 
    @lazy_wrapper(ResponsePayload)
    def on_response(self, peer: PeerType, payload: ResponsePayload) -> None:
        # Only trust the real server
        if peer.public_key.key_to_bin() != self._server_pubkey_bytes:
            print(f"⚠️  Ignoring response from unknown peer {peer}")
            return
 
        status = "✅  ACCEPTED" if payload.success else "❌  REJECTED"
        print(f"\n{status}")
        print(f"   Message: {payload.message}")
        self._done.set()
 
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
    else:
        print(f"🔑  Generating new key → {path}  (BACK THIS UP!)")
        key = default_eccrypto.generate_key("curve25519")
        with open(path, "wb") as f:
            f.write(key.key_to_bin())
        return key
 
# ─── Main ────────────────────────────────────
 
async def main(): 
    global _member_pubkeys
    keys = [load_or_create_key(k) for k in [KEY_FILE1, KEY_FILE2, KEY_FILE3]]
    _member_pubkeys = [k.pub().key_to_bin() for k in keys]
    builder = (
        ConfigBuilder()
        .clear_keys()
        .clear_overlays()
        .add_key("my_key", "curve25519", KEY_FILE1) 
        .add_overlay(
            "Lab2Community",
            "my_key",
            [WalkerDefinition(Strategy.RandomWalk, 50, {"timeout": 3.0})],
            default_bootstrap_defs,
            {},
            [("started",)],
        )
    )
 
    ipv8_instance = IPv8(
        builder.finalize(),
        extra_communities={"Lab2Community": Lab2Community},
    )
    await ipv8_instance.start()
    await asyncio.sleep(5)
    print("Walkable addresses known:", ipv8_instance.network.get_walkable_addresses())
 
    community: Lab2Community = ipv8_instance.get_overlay(Lab2Community)
 
    print("🌐  IPv8 started — searching for server peer…")
 
    await community.wait_for_response(timeout=600)
 
    await ipv8_instance.stop()
    print("\nDone.")
 


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    multiprocessing.freeze_support()
    asyncio.run(main())