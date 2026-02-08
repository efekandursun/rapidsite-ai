"""
FieldFlow AI - Procore Connector
Integration with Procore construction management software.
"""

import os
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

from connectors.base import (
    ERPConnector, 
    ERPError, 
    AuthenticationError, 
    ConnectionError, 
    SyncError
)


class ProcoreConnector(ERPConnector):
    """
    Procore ERP connector for Daily Log integration.
    
    Requires:
        - PROCORE_CLIENT_ID
        - PROCORE_CLIENT_SECRET
        - PROCORE_ACCESS_TOKEN (or use OAuth flow)
        - PROCORE_COMPANY_ID
    """
    
    # API URLs
    PRODUCTION_URL = "https://api.procore.com"
    SANDBOX_URL = "https://sandbox.procore.com"
    
    # Auth URLs
    AUTH_URL_PROD = "https://login.procore.com"
    AUTH_URL_SANDBOX = "https://login-sandbox.procore.com"
    
    def __init__(self, credentials: Dict[str, str] = None):
        """
        Initialize Procore connector.
        
        Args:
            credentials: Dict with:
                - client_id: OAuth Client ID
                - client_secret: OAuth Client Secret
                - redirect_uri: OAuth Redirect URI
                - access_token: OAuth access token (optional if doing auth flow)
                - refresh_token: OAuth refresh token (optional)
                - company_id: Procore company ID
                - use_sandbox: True to use sandbox environment
        """
        creds = credentials or {}
        
        self.client_id = creds.get('client_id') or os.getenv('PROCORE_CLIENT_ID')
        self.client_secret = creds.get('client_secret') or os.getenv('PROCORE_CLIENT_SECRET')
        self.redirect_uri = creds.get('redirect_uri') or os.getenv('PROCORE_REDIRECT_URI')
        
        self.access_token = creds.get('access_token') or os.getenv('PROCORE_ACCESS_TOKEN')
        self.refresh_token = creds.get('refresh_token') or os.getenv('PROCORE_REFRESH_TOKEN')
        self.company_id = creds.get('company_id') or os.getenv('PROCORE_COMPANY_ID')
        
        env_sandbox = os.getenv('PROCORE_USE_SANDBOX', '').lower() in ['1', 'true', 'yes']
        self.use_sandbox = creds.get('use_sandbox', env_sandbox)
        
        self.base_url = self.SANDBOX_URL if self.use_sandbox else self.PRODUCTION_URL
        self.auth_base_url = self.AUTH_URL_SANDBOX if self.use_sandbox else self.AUTH_URL_PROD
        
        super().__init__(creds)
    
    @property
    def name(self) -> str:
        return "Procore"
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get API headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Procore-Company-Id": str(self.company_id) if self.company_id else None,
            "Content-Type": "application/json"
        }
    
    def get_auth_url(self) -> str:
        """Generate OAuth2 authorization URL."""
        if not self.client_id or not self.redirect_uri:
            raise ERPError("Missing client_id or redirect_uri")
            
        return (
            f"{self.auth_base_url}/oauth/authorize"
            f"?client_id={self.client_id}"
            f"&response_type=code"
            f"&redirect_uri={self.redirect_uri}"
        )
    
    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange auth code for access token."""
        try:
            # Use data= for form-urlencoded, which is standard for OAuth
            response = requests.post(
                f"{self.auth_base_url}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri
                },
                timeout=15
            )
            
            # Debug info (remove in prod)
            if response.status_code != 200:
                print(f"Token exchange failed: {response.text}")
                
            response.raise_for_status()
            data = response.json()
            
            self.access_token = data.get('access_token')
            self.refresh_token = data.get('refresh_token')
            return data
            
        except requests.RequestException as e:
            raise AuthenticationError(f"Token exchange failed: {str(e)}")

    def refresh_access_token(self) -> Dict[str, Any]:
        """Refresh expired access token."""
        if not self.refresh_token:
            raise AuthenticationError("No refresh token available")
            
        try:
            response = requests.post(
                f"{self.auth_base_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "redirect_uri": self.redirect_uri
                },
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            self.access_token = data.get('access_token')
            self.refresh_token = data.get('refresh_token')
            return data
            
        except requests.RequestException as e:
            raise AuthenticationError(f"Token refresh failed: {str(e)}")

    def authenticate(self) -> bool:
        """
        Verify authentication is valid.
        Auto-refreshes token if expired (401).
        """
        if not self.access_token:
            raise AuthenticationError("No access token provided")
        
        try:
            response = requests.get(
                f"{self.base_url}/rest/v1.0/me",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self._authenticated = True
                return True
            elif response.status_code == 401 and self.refresh_token:
                # Try to refresh token
                print("🔄 Access token expired, refreshing...")
                self.refresh_access_token()
                # Retry request
                return self.authenticate()
            elif response.status_code == 401:
                raise AuthenticationError("Invalid or expired access token")
            else:
                raise AuthenticationError(f"Auth failed: {response.status_code}")
                
        except RecursionError:
            raise AuthenticationError("Repeated authentication failure")
        except requests.RequestException as e:
            raise ConnectionError(f"Connection failed: {str(e)}")
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            return self.authenticate()
        except ERPError:
            return False
    
    def get_companies(self) -> List[Dict[str, Any]]:
        """Get list of companies user has access to."""
        if not self._authenticated:
            self.authenticate()
            
        try:
            response = requests.get(
                f"{self.base_url}/rest/v1.0/companies",
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to get companies: {str(e)}")

    def get_projects(self, company_id: int = None) -> List[Dict[str, Any]]:
        """Get list of projects from Procore."""
        target_company_id = company_id or self.company_id
        if not target_company_id:
             # If no company ID, try to get first available company
             companies = self.get_companies()
             if companies:
                 target_company_id = companies[0]['id']
                 
        if not self._authenticated:
            self.authenticate()
        
        try:
            headers = self.headers.copy()
            if target_company_id:
                headers["Procore-Company-Id"] = str(target_company_id)
                
            response = requests.get(
                f"{self.base_url}/rest/v1.0/projects",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to get projects: {str(e)}")
    
    def push_daily_log(self, project_id: str, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push a daily log entry to Procore.
        
        Args:
            project_id: Procore project ID
            log_data: Our parsed report data
            
        Returns:
            Dict with success status and Procore log ID
        """
        if not self._authenticated:
            self.authenticate()
        
        # Transform our data to Procore format
        procore_data = self.transform_data(log_data)
        
        try:
            # Using 'notes_logs' as a generic daily log entry since specific types vary by project
            # Endpoint: POST /rest/v1.0/projects/{project_id}/notes_logs
            # Payload: { "notes_log": { "date": "...", "comment": "..." } }
            
            payload = {
                "notes_log": {
                    "date": procore_data.get("log_date"),
                    "comment": procore_data.get("description"),
                    "is_daily_log_header_note": False
                }
            }
            
            response = requests.post(
                f"{self.base_url}/rest/v1.0/projects/{project_id}/notes_logs",
                headers=self.headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                return {
                    "success": True,
                    "erp_id": result.get("id"),
                    "erp_response": result
                }
            else:
                raise SyncError(f"Procore rejected: {response.status_code} - {response.text}")
                
        except requests.RequestException as e:
            raise SyncError(f"Failed to push log: {str(e)}")
    
    def transform_data(self, our_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform our data format to Procore Daily Log format.
        """
        # Build description from our data
        description_parts = []
        
        if our_data.get('item'):
            description_parts.append(our_data['item'])
        
        if our_data.get('quantity') and our_data.get('unit'):
            description_parts.append(f"- {our_data['quantity']} {our_data['unit']}")
        
        if our_data.get('description'):
            description_parts.append(our_data['description'])
        
        if our_data.get('location'):
            loc = our_data['location']
            if isinstance(loc, dict):
                loc_str = ", ".join(filter(None, [
                    loc.get('building'),
                    loc.get('level'),
                    loc.get('area')
                ]))
            else:
                loc_str = str(loc)
            if loc_str:
                description_parts.append(f"Location: {loc_str}")
        
        return {
            "log_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "description": " | ".join(description_parts) or "Field report"
        }


# --- TEST SECTION ---
if __name__ == "__main__":
    print("=" * 60)
    print("Procore Connector Test")
    print("=" * 60)
    
    # Test with mock data (no actual API call)
    connector = ProcoreConnector({
        "access_token": "test-token",
        "company_id": "12345",
        "use_sandbox": True
    })
    
    # Test data transformation
    test_data = {
        "log_type": "production",
        "item": "Concrete Pour",
        "quantity": 150,
        "unit": "CY",
        "description": "Completed ahead of schedule",
        "location": {
            "building": "A",
            "level": "2",
            "area": "Parking Deck"
        }
    }
    
    transformed = connector.transform_data(test_data)
    print(f"\nInput: {test_data}")
    print(f"\nProcore format: {transformed}")
