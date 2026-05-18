from ipv8.keyvault.crypto import default_eccrypto

# Load your existing private key
with open("my_key.pem", "rb") as f:
    key_data = f.read()

key = default_eccrypto.key_from_private_bin(key_data)

# Extract public key
public_key_hex = key.pub().key_to_bin().hex()
print("Your public key (hex):", public_key_hex)