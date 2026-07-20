"""
RapidSite AI - Procore Connector
Integration with Procore construction management software.
"""

import os
import json
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime
from core.utils import retry_on_exception

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
    
    def get_auth_url(self, state: str = None) -> str:
        """Generate OAuth2 authorization URL."""
        if not self.client_id or not self.redirect_uri:
            raise ERPError("Missing client_id or redirect_uri")
            
        url = (
            f"{self.auth_base_url}/oauth/authorize"
            f"?client_id={self.client_id}"
            f"&response_type=code"
            f"&redirect_uri={self.redirect_uri}"
        )
        if state:
            url += f"&state={state}"
        return url
    
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
        
        if not self._authenticated:
            self.authenticate()
            
        if not target_company_id:
              # If no company ID, try to get first available company
              companies = self.get_companies()
              if companies:
                  target_company_id = companies[0]['id']
        
        try:
            headers = self.headers.copy()
            # Important: Procore-Company-Id must be in headers for this endpoint
            if target_company_id:
                headers["Procore-Company-Id"] = str(target_company_id)
                
            response = requests.get(
                f"{self.base_url}/rest/v1.0/projects",
                headers=headers,
                params={"company_id": target_company_id} if target_company_id else {},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            print(f"Failed to get projects: {e}")
            return []

    def get_locations(self, project_id: str) -> List[Dict[str, Any]]:
        """Fetch project locations from Procore."""
        if not self._authenticated:
            self.authenticate()
            
        try:
            url = f"{self.base_url}/rest/v1.0/projects/{project_id}/locations"
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"⚠️ Failed to fetch locations: {e}")
        return []

    def find_location_id(self, project_id: str, log_data: Dict[str, Any]) -> Optional[int]:
        """Try to match AI location string to a Procore Location ID."""
        # Extract location string from AI data
        loc_data = log_data.get('location')
        if not loc_data:
            return None
            
        search_str = ""
        if isinstance(loc_data, dict):
            # Prefer 'name' if available, else build from parts
            search_str = loc_data.get('name') or " ".join(filter(None, [
                loc_data.get('building'),
                loc_data.get('level'), 
                loc_data.get('area')
            ]))
        elif isinstance(loc_data, str):
            search_str = loc_data
            
        if not search_str:
            return None
            
        search_lower = search_str.lower().strip()
        print(f"📍 Searching for location: '{search_str}'...")

        # Fetch Procore locations
        locations = self.get_locations(project_id)
        
        # Strategy 1: Exact Match (Name or Node Name)
        for loc in locations:
            if loc['name'].lower() == search_lower or loc.get('node_name', '').lower() == search_lower:
                print(f"✅ Exact location match: {loc['name']} (ID: {loc['id']})")
                return loc['id']

        # Strategy 2: Contains Match (AI string inside Procore path)
        # e.g. AI: "Building A" -> Procore: "Building A > Level 1" (Maybe risky, let's do reverse)
        
        # Strategy 3: Reverse Contains (Procore Path inside AI string?? No)
        
        # Strategy 3: Part Match
        # If AI says "Building A Level 2", and Procore has "Building A > Level 2", match it.
        # Normalize Procore name: "Building A > Level 2" -> "building a level 2"
        for loc in locations:
            normalized_name = loc['name'].replace(">", "").replace("-", " ").lower()
            # aggressive normalization
            normalized_name = " ".join(normalized_name.split())
            
            if search_lower in normalized_name or normalized_name in search_lower:
                print(f"✅ Fuzzy location match: '{loc['name']}' for input '{search_str}'")
                return loc['id']

            print(f"⚠️ No location match found for '{search_str}'")
        return None

    def get_uoms(self) -> List[Dict[str, Any]]:
        """Fetch company Units of Measure from Procore."""
        if not self._authenticated:
            self.authenticate()
            
        if not self.company_id:
            return []
            
        try:
            url = f"{self.base_url}/rest/v1.0/companies/{self.company_id}/uoms"
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"⚠️ Failed to fetch UOMs: {e}")
        return []

    def find_uom_id(self, unit_str: str) -> Optional[int]:
        """Map AI unit string (CY, ea, tons) to Procore UOM ID."""
        if not unit_str: return None
        
        search_lower = unit_str.lower().strip()
        
        # Standard mappings because AI output vs Procore names differ
        # AI -> Procore Name expected
        common_mappings = {
            "cy": "cubic yards",
            "cubic yard": "cubic yards",
            "ea": "each",
            "lf": "linear feet",
            "sf": "square feet",
            "ls": "lump sum",
            "hr": "hours"
        }
        
        # Normalize search string via mapping if possible
        target_name = common_mappings.get(search_lower, search_lower)
        
        print(f"📏 Searching for UOM: '{unit_str}' (Target: '{target_name}')")
        
        uoms = self.get_uoms()
        
        for uom in uoms:
            uom_name = uom['name'].lower()
            # Exact match on name or mapped name
            if uom_name == target_name or uom_name == search_lower:
                print(f"✅ UOM match: {uom['name']} (ID: {uom['id']})")
                return uom['id']
                
            # Match on abbreviation/key if available in Procore response (usually just name/desc)
            if uom.get('description') and uom['description'].lower() == target_name:
                print(f"✅ UOM match by desc: {uom['name']} (ID: {uom['id']})")
                return uom['id']
                
        print(f"⚠️ No UOM match for '{unit_str}'")
        return None
    
    def get_vendors(self, project_id: str) -> List[Dict[str, Any]]:
        """Fetch project vendors upon request."""
        if not self._authenticated: self.authenticate()
        try:
            url = f"{self.base_url}/rest/v1.0/projects/{project_id}/vendors"
            response = requests.get(url, headers=self.headers, params={"company_id": self.company_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
        except: pass
        return []

    def find_vendor_id(self, project_id: str, company_name: str) -> Optional[int]:
        """Fuzzy match company name to Procore Vendor ID."""
        if not company_name: return None
        search = company_name.lower().strip()
        print(f"🏢 Searching for Vendor: '{company_name}'")
        
        vendors = self.get_vendors(project_id)
        for v in vendors:
            v_name = v['name'].lower()
            if search in v_name or v_name in search:
                print(f"✅ Vendor match: {v['name']} (ID: {v['id']})")
                return v['id']
        print(f"⚠️ No Vendor match for '{company_name}'")
        return None

    def get_cost_codes(self, project_id: str) -> List[Dict[str, Any]]:
        """Fetch project cost codes."""
        if not self._authenticated: self.authenticate()
        try:
            url = f"{self.base_url}/rest/v1.0/projects/{project_id}/cost_codes"
            response = requests.get(url, headers=self.headers, params={"company_id": self.company_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
        except: pass
        return []

    def find_cost_code_id(self, project_id: str, search_str: str) -> Optional[int]:
        """Fuzzy match work description to Cost Code ID."""
        if not search_str: return None
        search = search_str.lower().strip()
        print(f"💰 Searching for Cost Code: '{search_str}'")
        
        codes = self.get_cost_codes(project_id)
        best_match = None
        
        for code in codes:
            # Match against name (e.g. "Cast-in-Place Concrete")
            name = code['name'].lower()
            full_code = f"{code['code']} {name}".lower() # "03-3000 cast-in-place concrete"
            
            if search in name or name in search:
                print(f"✅ Cost Code match: {code['name']} (ID: {code['id']})")
                return code['id']
                
        print(f"⚠️ No Cost Code match for '{search_str}'")
        return None

    @retry_on_exception(exceptions=(requests.RequestException,), max_retries=2, initial_delay=1.0)
    def push_daily_log(self, project_id: str, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push a daily log entry to the correct Procore Daily Log category.
        Routes based on log_type: manpower, equipment, materials/production, or notes.
        """
        if not self._authenticated:
            self.authenticate()
            
        # Ensure we have a company ID
        if not self.company_id:
            print("⚠️ No company_id found, attempting to auto-detect...")
            companies = self.get_companies()
            if companies:
                self.company_id = companies[0]['id']
                print(f"✅ Auto-detected company_id: {self.company_id}")
            else:
                 print("❌ Failed to auto-detect company_id")
        
        # Determine which endpoint & payload to use based on log_type
        if not log_data: log_data = {}
        log_type = (log_data.get('log_type') or 'notes').lower()
        log_date = datetime.utcnow().strftime("%Y-%m-%d")

        location_id = self.find_location_id(project_id, log_data)
        
        # 📏 Try to find UOM ID if quantity log
        uom_id = None
        if log_type in ("materials", "production", "delivery", "quantity"):
             unit_str = log_data.get('unit') or (log_data.get('delivery_details') or {}).get('unit')
             if unit_str:
                 uom_id = self.find_uom_id(unit_str)

        # 🏢 Try to find Vendor ID (Manpower, Delivery)
        vendor_id = None
        company_name = (log_data.get('crew') or {}).get('company_name') or (log_data.get('delivery_details') or {}).get('delivery_from')
        if company_name:
            vendor_id = self.find_vendor_id(project_id, company_name)
            
        # 💰 Try to find Cost Code ID (Quantities, Manpower, Equipment)
        cost_code_id = None
        # Use 'item' or 'trade' or 'description' as search query
        search_query = log_data.get('item') or (log_data.get('crew') or {}).get('trade') or log_data.get('description')
        if search_query:
            cost_code_id = self.find_cost_code_id(project_id, search_query)

        endpoint, payload, category_label = self._build_category_payload(
            log_type, log_data, log_date, location_id, uom_id, vendor_id, cost_code_id
        )
        
        url = f"{self.base_url}/rest/v1.0/projects/{project_id}/{endpoint}"
        
        print(f"🔄 Syncing to Procore...")
        print(f"📂 Category: {category_label}")
        print(f"📍 URL: {url}")
        print(f"🆔 Project ID: {project_id}")
        print(f"🏢 Company Header: {self.headers.get('Procore-Company-Id')}")
        print(f"📦 Payload: {payload}")
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                print(f"✅ Procore {category_label} response: {json.dumps(result, indent=2, default=str)[:500]}")
                return {
                    "success": True,
                    "erp_id": result.get("id"),
                    "erp_response": result,
                    "category": category_label
                }
            else:
                print(f"❌ Procore {category_label} error response: {response.text[:500]}")
                # If category endpoint fails, fallback to Notes
                if endpoint != "notes_logs":
                    print(f"⚠️ {category_label} endpoint failed ({response.status_code}), falling back to Notes...")
                    print(f"📝 Fallback -> Notes: {url}")
                    return self._push_as_note(project_id, log_data, log_date)
                raise SyncError(f"Procore rejected: {response.status_code} - {response.text}")
                
        except requests.RequestException as e:
            raise SyncError(f"Failed to push log: {str(e)}")

    def _build_category_payload(self, log_type: str, log_data: Dict[str, Any], log_date: str, 
                                location_id: Optional[int] = None, 
                                uom_id: Optional[int] = None,
                                vendor_id: Optional[int] = None,
                                cost_code_id: Optional[int] = None):
        """Build the correct endpoint and payload based on log_type."""
        
        description = self._build_description(log_data)
        
        # Helper helpers
        def add_loc(target_dict):
            if location_id: target_dict['location_id'] = location_id
        def add_uom(target_dict):
            if uom_id: target_dict['unit_of_measure_id'] = uom_id
        def add_vendor(target_dict):
            if vendor_id: target_dict['vendor_id'] = vendor_id
        def add_cost_code(target_dict):
            if cost_code_id: target_dict['cost_code_id'] = cost_code_id
        
        if log_type == "manpower":
            # Extract from new 'crew' object if available
            crew = log_data.get('crew') or {}
            num_workers = crew.get('count') or log_data.get('quantity') or 1
            trade = crew.get('trade') or log_data.get('item', '')
            hours = crew.get('hours') or 8
            company = crew.get('company_name', '')
            
            desc_str = description
            if company and not vendor_id:
                desc_str = f"Sub: {company} | {desc_str}"

            payload = {
                "manpower_log": {
                    "date": log_date,
                    "num_workers": num_workers,
                    "num_hours": hours,
                    "notes": f"{trade} - {desc_str}" if trade else desc_str
                }
            }
            add_loc(payload['manpower_log'])
            add_vendor(payload['manpower_log'])
            add_cost_code(payload['manpower_log'])
            return "manpower_logs", payload, "Manpower"
        
        elif log_type == "equipment":
            equipment_name = log_data.get('item', 'Equipment')
            
            # Extract details
            details = log_data.get('equipment_details') or {}
            hours_op = details.get('hours_operating') or log_data.get('quantity') or 0
            hours_idle = details.get('hours_idle') or 0
            inspected = details.get('inspected', False)
            
            notes = f"{equipment_name} - {hours_op}h op / {hours_idle}h idle | {description}"

            payload = {
                "equipment_log": {
                    "date": log_date,
                    "log_date": log_date,
                    "equipment_name": equipment_name,
                    "hours_operating": float(hours_op),
                    "hours_idle": float(hours_idle),
                    "inspected": inspected,
                    "notes": notes
                }
            }
            add_loc(payload['equipment_log'])
            add_cost_code(payload['equipment_log'])
            return "equipment_logs", payload, "Equipment"
        
        elif log_type in ("materials", "production"):
            quantity = log_data.get('quantity') or 0
            unit = log_data.get('unit', 'EA')
            item = log_data.get('item', 'Material')
            
            payload = {
                "quantity_log": {
                    "date": log_date,
                    "log_date": log_date,
                    "quantity": float(quantity) if quantity else 0.0,
                    # "units": str(unit), # Deprecated if uom_id works, but keep for fallback? Procore API prefers uom_id
                    "description": f"{item} - {quantity} {unit} | {description}"
                }
            }
            add_loc(payload['quantity_log'])
            add_uom(payload['quantity_log'])
            add_cost_code(payload['quantity_log'])
            return "quantity_logs", payload, "Quantities"
        
        elif log_type == "delivery":
            quantity = log_data.get('quantity') or 0
            unit = log_data.get('unit') or 'EA'
            item = log_data.get('item', 'Delivery')
            
            details = log_data.get('delivery_details') or {}
            tracking = details.get('tracking_number', '')
            vendor = details.get('delivery_from', '')
            dev_time = details.get('time', '')
            
            # Combine info into description since some ID fields (vendor_id) might not be resolvable
            full_desc = f"{item} - {quantity} {unit}"
            if vendor: full_desc += f" from {vendor}"
            if tracking: full_desc += f" (Trk#{tracking})"
            if dev_time: full_desc += f" @ {dev_time}"
            
            payload = {
                "delivery_log": {
                    "date": log_date,
                    "log_date": log_date,
                    "status": "pending",
                    "delivery_from": vendor,
                    "tracking_number": tracking,
                    "contents": f"{item} - {quantity} {unit}",
                    "description": full_desc,
                    "comments": f"{full_desc} | {description}"
                }
            }
            add_loc(payload['delivery_log'])
            add_vendor(payload['delivery_log'])
            # Try to add time if available (Procore requires time_hour and time_minute)
            if dev_time and ':' in dev_time:
                try:
                    h, m = dev_time.split(':')
                    payload['delivery_log']['time_hour'] = int(h)
                    payload['delivery_log']['time_minute'] = int(m)
                except: 
                    payload['delivery_log']['time_hour'] = 12
                    payload['delivery_log']['time_minute'] = 0
            else:
                payload['delivery_log']['time_hour'] = 12
                payload['delivery_log']['time_minute'] = 0

            return "delivery_logs", payload, "Deliveries"
        
        elif log_type == "safety":
            item = log_data.get('item', 'Safety Issue')
            now = datetime.utcnow()
            
            details = log_data.get('safety_details') or {}
            notice = details.get('safety_notice', '')
            issued_to = details.get('issued_to', '')
            compliance_due = details.get('compliance_due', '')

            comments = f"{item} | {description}"
            if notice: comments += f" | Notice: {notice}"
            if issued_to: comments += f" | Issued To: {issued_to}"
            
            payload = {
                "safety_violation_log": {
                    "date": log_date,
                    "log_date": log_date,
                    "time_hour": now.hour,
                    "time_minute": now.minute,
                    "title": item,
                    "subject": item,
                    "safety_notice": notice,
                    "issued_to": issued_to,
                    "compliance_due": compliance_due,
                    "description": comments,
                    "comments": comments,
                    "status": "pending"
                }
            }
            add_loc(payload['safety_violation_log'])
            return "safety_violation_logs", payload, "Safety Violations"
        
        else:
            # notes or any unknown type -> Notes
            is_issue = log_data.get('is_issue', False) or 'issue' in description.lower() or 'safety' in description.lower()
            
            payload = {
                "notes_log": {
                    "date": log_date,
                    "comment": description,
                    "is_issue": is_issue,
                    "is_daily_log_header_note": False
                }
            }
            add_loc(payload['notes_log'])
            return "notes_logs", payload, "Notes"

    def _push_as_note(self, project_id: str, log_data: Dict[str, Any], log_date: str):
        """Fallback: push as a Note log entry."""
        description = self._build_description(log_data)
        payload = {
            "notes_log": {
                "date": log_date,
                "comment": description,
                "is_daily_log_header_note": False
            }
        }
        url = f"{self.base_url}/rest/v1.0/projects/{project_id}/notes_logs"
        print(f"📝 Fallback -> Notes: {url}")
        
        response = requests.post(url, headers=self.headers, json=payload, timeout=15)
        
        if response.status_code in [200, 201]:
            result = response.json()
            return {
                "success": True,
                "erp_id": result.get("id"),
                "erp_response": result,
                "category": "Notes (fallback)"
            }
        raise SyncError(f"Procore rejected: {response.status_code} - {response.text}")

    def _build_description(self, log_data: Dict[str, Any]) -> str:
        """Build a human-readable description from parsed data."""
        parts = []
        
        if log_data.get('item'):
            parts.append(log_data['item'])
        
        if log_data.get('quantity') and log_data.get('unit'):
            parts.append(f"- {log_data['quantity']} {log_data['unit']}")
        
        if log_data.get('description'):
            parts.append(log_data['description'])
        
        if log_data.get('location'):
            loc = log_data['location']
            if isinstance(loc, dict):
                loc_str = ", ".join(filter(None, [
                    loc.get('building'),
                    loc.get('level'),
                    loc.get('area')
                ]))
            else:
                loc_str = str(loc)
            if loc_str:
                parts.append(f"Location: {loc_str}")
        
        return " | ".join(parts) or "Field report"


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
