"""
Authentication Module
Handles wallet signing and API credential management for Polymarket
"""

from typing import Optional, Tuple
from eth_account import Account
from eth_account.messages import encode_defunct
from loguru import logger
import time


class AuthManager:
    """
    Manages authentication for Polymarket CLOB API

    Handles:
    - Wallet key management
    - Message signing for API authentication
    - API credential derivation
    """

    def __init__(
        self,
        private_key: str,
        proxy_wallet_address: Optional[str] = None,
        signature_type: int = 1
    ):
        """
        Initialize authentication manager

        Args:
            private_key: Ethereum private key (with or without 0x prefix)
            proxy_wallet_address: Polymarket proxy wallet address (from profile)
            signature_type: 0=EOA/MetaMask, 1=Email/Magic, 2=Browser Proxy
        """
        self.private_key = self._normalize_key(private_key)
        self.proxy_wallet_address = proxy_wallet_address
        self.signature_type = signature_type
        self._account = Account.from_key(self.private_key)

    @property
    def address(self) -> str:
        """Get the wallet address"""
        return self._account.address

    @property
    def funder_address(self) -> str:
        """Get the funder address (proxy wallet if set, otherwise main wallet)"""
        return self.proxy_wallet_address or self._account.address

    def _normalize_key(self, key: str) -> str:
        """Ensure private key has 0x prefix"""
        if not key.startswith("0x"):
            key = "0x" + key
        return key

    def sign_message(self, message: str) -> str:
        """
        Sign a message with the wallet

        Args:
            message: Message to sign

        Returns:
            Signature string
        """
        try:
            message_encoded = encode_defunct(text=message)
            signed = self._account.sign_message(message_encoded)
            return signed.signature.hex()
        except Exception as e:
            logger.error(f"Failed to sign message: {e}")
            raise

    def generate_api_key_message(self, nonce: int) -> str:
        """
        Generate message for API key derivation

        Args:
            nonce: Nonce value (usually timestamp)

        Returns:
            Message string to sign
        """
        return f"Polymarket API Key\n\nNonce: {nonce}"

    def create_api_credentials(self) -> Tuple[str, str, str]:
        """
        Create or derive API credentials for Polymarket

        Returns:
            Tuple of (api_key, api_secret, passphrase)
        """
        nonce = int(time.time() * 1000)
        message = self.generate_api_key_message(nonce)
        signature = self.sign_message(message)

        # The actual derivation happens in the CLOB client
        # This is a placeholder showing the signing process
        logger.info("API credentials derived from wallet signature")

        return (signature[:32], signature[32:64], signature[64:])

    def sign_order(self, order_data: dict) -> str:
        """
        Sign an order for submission

        Args:
            order_data: Order data dictionary

        Returns:
            Order signature
        """
        # Order signing is handled by py-clob-client
        # This method provides the signing capability
        import json
        order_str = json.dumps(order_data, sort_keys=True)
        return self.sign_message(order_str)

    def verify_signature(self, message: str, signature: str, address: str) -> bool:
        """
        Verify a signature matches an address

        Args:
            message: Original message
            signature: Signature to verify
            address: Expected signer address

        Returns:
            True if signature is valid
        """
        try:
            message_encoded = encode_defunct(text=message)
            recovered = Account.recover_message(message_encoded, signature=signature)
            return recovered.lower() == address.lower()
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
