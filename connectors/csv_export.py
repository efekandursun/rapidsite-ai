"""
RapidSite AI - CSV Export Connector
Fallback connector for exporting reports to CSV files.
"""

import os
import csv
from datetime import datetime
from typing import Dict, Any, List

from connectors.base import ERPConnector


class CSVExportConnector(ERPConnector):
    """
    CSV export connector - fallback when no ERP is configured.
    
    Exports reports to CSV files that can be manually imported
    into any ERP system.
    """
    
    def __init__(self, credentials: Dict[str, str] = None):
        """
        Initialize CSV connector.
        
        Args:
            credentials: Dict with:
                - export_path: Directory for CSV files (default: ./exports)
        """
        creds = credentials or {}
        self.export_path = creds.get('export_path') or os.getenv('CSV_EXPORT_PATH', './exports')
        self._ensure_export_dir()
        
        super().__init__(creds)
        self._authenticated = True  # CSV doesn't need auth
    
    def _ensure_export_dir(self):
        """Create export directory if it doesn't exist."""
        if not os.path.exists(self.export_path):
            os.makedirs(self.export_path)
    
    @property
    def name(self) -> str:
        return "CSV Export"
    
    def authenticate(self) -> bool:
        """CSV doesn't need authentication."""
        self._authenticated = True
        return True
    
    def test_connection(self) -> bool:
        """Test if export directory is writable."""
        try:
            test_file = os.path.join(self.export_path, ".test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.unlink(test_file)
            return True
        except Exception:
            return False
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """Return empty list - CSV doesn't have projects."""
        return []
    
    def push_daily_log(self, project_id: str, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Export log to CSV file.
        
        Creates/appends to a CSV file named by project and date.
        """
        # Generate filename
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        filename = f"reports_{project_id}_{date_str}.csv"
        filepath = os.path.join(self.export_path, filename)
        
        # Check if file exists (for header row)
        file_exists = os.path.exists(filepath)
        
        # Flatten data for CSV
        flat_data = self._flatten_data(log_data)
        
        # Write to CSV
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=flat_data.keys())
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(flat_data)
        
        return {
            "success": True,
            "erp_id": f"CSV-{datetime.utcnow().strftime('%H%M%S')}",
            "file_path": filepath
        }
    
    def _flatten_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten nested data for CSV export."""
        flat = {
            "timestamp": datetime.utcnow().isoformat(),
            "log_type": data.get("log_type", ""),
            "item": data.get("item", ""),
            "quantity": data.get("quantity", ""),
            "unit": data.get("unit", ""),
            "cost_code": data.get("cost_code", ""),
            "cost_code_description": data.get("cost_code_description", ""),
            "description": data.get("description", ""),
            "urgency": data.get("urgency", ""),
        }
        
        # Flatten location
        location = data.get("location", {})
        if isinstance(location, dict):
            flat["location_building"] = location.get("building", "")
            flat["location_level"] = location.get("level", "")
            flat["location_area"] = location.get("area", "")
        else:
            flat["location"] = str(location) if location else ""
        
        # Flatten crew
        crew = data.get("crew", {})
        if isinstance(crew, dict):
            flat["crew_count"] = crew.get("count", "")
            flat["crew_trade"] = crew.get("trade", "")
        
        # Equipment as comma-separated
        equipment = data.get("equipment", [])
        flat["equipment"] = ", ".join(equipment) if isinstance(equipment, list) else str(equipment)
        
        return flat
    
    def get_all_exports(self) -> List[str]:
        """Get list of all export files."""
        files = []
        for f in os.listdir(self.export_path):
            if f.endswith('.csv'):
                files.append(os.path.join(self.export_path, f))
        return sorted(files, reverse=True)


# --- TEST SECTION ---
if __name__ == "__main__":
    import tempfile
    import shutil
    
    print("=" * 60)
    print("CSV Export Connector Test")
    print("=" * 60)
    
    # Use temp directory for testing
    test_dir = tempfile.mkdtemp()
    
    try:
        connector = CSVExportConnector({"export_path": test_dir})
        
        # Test data
        test_data = {
            "log_type": "production",
            "item": "Concrete Pour",
            "quantity": 150,
            "unit": "CY",
            "cost_code": "03-30-00",
            "location": {
                "building": "A",
                "level": "2"
            },
            "crew": {
                "count": 8,
                "trade": "Concrete"
            },
            "equipment": ["Pump Truck", "Vibrator"]
        }
        
        # Export
        result = connector.push_daily_log("PRJ-001", test_data)
        print(f"\n✅ Export result: {result}")
        
        # Check file
        files = connector.get_all_exports()
        print(f"\n📁 Exported files: {files}")
        
        # Read content
        with open(files[0], 'r') as f:
            print(f"\n📄 File content:\n{f.read()}")
            
    finally:
        # Cleanup
        shutil.rmtree(test_dir)
        print(f"\n🧹 Test directory cleaned up")
