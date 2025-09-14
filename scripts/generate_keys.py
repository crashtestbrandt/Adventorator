#!/usr/bin/env python3

import nacl.signing

signing_key = nacl.signing.SigningKey.generate()
verify_key = signing_key.verify_key

print("Add these to your .env file (dev CLI only):")
print(f"DISCORD_DEV_PUBLIC_KEY={verify_key.encode(encoder=nacl.encoding.HexEncoder).decode('utf-8')}")
print(f"DISCORD_PRIVATE_KEY={signing_key.encode(encoder=nacl.encoding.HexEncoder).decode('utf-8')}")