# sso_auth.py - Single Sign-On authentication providers
import os
from typing import Optional, Dict, Any
from structured_logging import get_logger
from fastapi import HTTPException

logger = get_logger("sso_auth")

class SSOProvider:
    """Base SSO provider"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
    
    async def authenticate(self, code: str) -> Dict[str, Any]:
        """Authenticate with provider"""
        raise NotImplementedError

class AzureADProvider(SSOProvider):
    """Microsoft Azure AD authentication"""
    
    def __init__(self):
        super().__init__(
            client_id=os.getenv("AZURE_AD_CLIENT_ID"),
            client_secret=os.getenv("AZURE_AD_CLIENT_SECRET")
        )
        self.tenant_id = os.getenv("AZURE_AD_TENANT_ID", "common")
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
    
    async def authenticate(self, code: str) -> Dict[str, Any]:
        """Authenticate with Azure AD"""
        import aiohttp
        
        token_url = f"{self.authority}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": os.getenv("AZURE_AD_REDIRECT_URI"),
            "grant_type": "authorization_code",
            "scope": "openid profile email"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=data) as resp:
                    if resp.status != 200:
                        raise HTTPException(status_code=401, detail="Azure AD authentication failed")
                    
                    token_data = await resp.json()
                    
                    logger.info("Azure AD authentication successful")
                    return {
                        "provider": "azure_ad",
                        "access_token": token_data.get("access_token"),
                        "email": token_data.get("email"),
                        "name": token_data.get("name")
                    }
        
        except Exception as e:
            logger.error("Azure AD authentication error", error=str(e))
            raise HTTPException(status_code=401, detail="Authentication failed")

class GoogleProvider(SSOProvider):
    """Google OAuth authentication"""
    
    def __init__(self):
        super().__init__(
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
        )
    
    async def authenticate(self, code: str) -> Dict[str, Any]:
        """Authenticate with Google"""
        import aiohttp
        
        token_url = "https://oauth2.googleapis.com/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
            "grant_type": "authorization_code"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=data) as resp:
                    if resp.status != 200:
                        raise HTTPException(status_code=401, detail="Google authentication failed")
                    
                    token_data = await resp.json()
                    
                    logger.info("Google authentication successful")
                    return {
                        "provider": "google",
                        "access_token": token_data.get("access_token"),
                        "id_token": token_data.get("id_token")
                    }
        
        except Exception as e:
            logger.error("Google authentication error", error=str(e))
            raise HTTPException(status_code=401, detail="Authentication failed")

class OktaProvider(SSOProvider):
    """Okta authentication"""
    
    def __init__(self):
        super().__init__(
            client_id=os.getenv("OKTA_CLIENT_ID"),
            client_secret=os.getenv("OKTA_CLIENT_SECRET")
        )
        self.org_url = os.getenv("OKTA_ORG_URL")
    
    async def authenticate(self, code: str) -> Dict[str, Any]:
        """Authenticate with Okta"""
        import aiohttp
        
        token_url = f"{self.org_url}/oauth2/v1/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": os.getenv("OKTA_REDIRECT_URI"),
            "grant_type": "authorization_code"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=data) as resp:
                    if resp.status != 200:
                        raise HTTPException(status_code=401, detail="Okta authentication failed")
                    
                    token_data = await resp.json()
                    
                    logger.info("Okta authentication successful")
                    return {
                        "provider": "okta",
                        "access_token": token_data.get("access_token"),
                        "id_token": token_data.get("id_token")
                    }
        
        except Exception as e:
            logger.error("Okta authentication error", error=str(e))
            raise HTTPException(status_code=401, detail="Authentication failed")

class SSOManager:
    """Manage SSO providers"""
    
    def __init__(self):
        self.providers: Dict[str, SSOProvider] = {}
        self._init_providers()
    
    def _init_providers(self):
        """Initialize SSO providers based on environment"""
        if os.getenv("AZURE_AD_CLIENT_ID"):
            self.providers["azure_ad"] = AzureADProvider()
            logger.info("Azure AD provider initialized")
        
        if os.getenv("GOOGLE_CLIENT_ID"):
            self.providers["google"] = GoogleProvider()
            logger.info("Google provider initialized")
        
        if os.getenv("OKTA_CLIENT_ID"):
            self.providers["okta"] = OktaProvider()
            logger.info("Okta provider initialized")
    
    async def authenticate(self, provider: str, code: str) -> Dict[str, Any]:
        """Authenticate with specified provider"""
        if provider not in self.providers:
            raise HTTPException(status_code=400, detail=f"Provider {provider} not configured")
        
        return await self.providers[provider].authenticate(code)
    
    def get_providers(self):
        """Get list of available providers"""
        return list(self.providers.keys())

# Global SSO manager
_sso_manager = None

def get_sso_manager() -> SSOManager:
    """Get SSO manager instance"""
    global _sso_manager
    if not _sso_manager:
        _sso_manager = SSOManager()
    return _sso_manager
