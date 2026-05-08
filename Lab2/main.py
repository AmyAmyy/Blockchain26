import asyncio
import multiprocessing
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
from ipv8_service import IPv8
from lab2_community import Lab2Community

 # ─── Main ────────────────────────────────────
 
async def main():    
    builder = (
        ConfigBuilder()
        .clear_keys()
        .clear_overlays()
        .add_key("my_key", "curve25519", "my_key.pem") # Change this to own key
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
 
    community: Lab2Community = ipv8_instance.get_overlay(Lab2Community)
 
    print("🌐  IPv8 started — searching for server peer…")
 
    await community.wait_for_response(timeout=600)
 
    await ipv8_instance.stop()
    print("\nDone.")
 


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    multiprocessing.freeze_support()
    asyncio.run(main())