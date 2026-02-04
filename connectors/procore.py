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
    OAUTH_URL = "https://login.procore.com"
    
    def __init__(self, credentials: Dict[str, str] = None):
        """
        Initialize Procore connector.
        
        Args:
            credentials: Dict with:
                - access_token: OAuth access token
                - company_id: Procore company ID
                - use_sandbox: True to use sandbox environment
        """
        creds = credentials or {}
        
        # Load from env if not provided
        self.access_token = creds.get('access_token') or os.getenv('PROCORE_ACCESS_TOKEN')
        self.company_id = creds.get('company_id') or os.getenv('PROCORE_COMPANY_ID')
        self.use_sandbox = creds.get('use_sandbox', False)
        
        self.base_url = self.SANDBOX_URL if self.use_sandbox else self.PRODUCTION_URL
        
        super().__init__(creds)
    
    @property
    def name(self) -> str:
        return "Procore"
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get API headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Procore-Company-Id": str(self.company_id),
            "Content-Type": "application/json"
        }
    
    def authenticate(self) -> bool:
        """
        Verify authentication is valid.
        
        For full OAuth flow, use the separate OAuth handler.
        This just verifies the token works.
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
            elif response.status_code == 401:
                raise AuthenticationError("Invalid or expired access token")
            else:
                raise AuthenticationError(f"Auth failed: {response.status_code}")
                
        except requests.RequestException as e:
            raise ConnectionError(f"Connection failed: {str(e)}")
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            return self.authenticate()
        except ERPError:
            return False
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """Get list of projects from Procore."""
        if not self._authenticated:
            self.authenticate()
        
        try:
            response = requests.get(
                f"{self.base_url}/rest/v1.0/projects",
                headers=self.headers,
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
            response = requests.post(
                f"{self.base_url}/rest/v1.0/projects/{project_id}/daily_construction_report_logs",
                headers=self.headers,
                json={"daily_construction_report_log": procore_data},
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
        
        Our format:
        {
            "log_type": "production",
            "description": "Poured 150 CY concrete",
            "item": "Concrete Pour",
            "quantity": 150,
            "unit": "CY",
            ...
        }
        
        Procore format:
        {
            "log_date": "2024-02-02",
            "description": "...",
            ...
        }
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
