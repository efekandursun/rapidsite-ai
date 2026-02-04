"""
FieldFlow AI - ERP Connector Base
Abstract base class for ERP integrations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class ERPConnector(ABC):
    """
    Abstract base class for ERP integrations.
    
    Implement this class to add support for new ERP systems.
    Only need to implement ~3-4 methods per ERP.
    """
    
    def __init__(self, credentials: Dict[str, str]):
        """
        Initialize connector with credentials.
        
        Args:
            credentials: Dict with ERP-specific auth info
                        (API keys, OAuth tokens, etc.)
        """
        self.credentials = credentials
        self._authenticated = False
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the ERP system name."""
        pass
    
    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with the ERP system.
        
        Returns:
            True if authentication successful
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test if the connection is working.
        
        Returns:
            True if connection is healthy
        """
        pass
    
    @abstractmethod
    def get_projects(self) -> List[Dict[str, Any]]:
        """
        Get list of projects from ERP.
        
        Returns:
            List of project dictionaries
        """
        pass
    
    @abstractmethod
    def push_daily_log(self, project_id: str, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push a daily log entry to the ERP.
        
        Args:
            project_id: ERP project identifier
            log_data: Our parsed report data
            
        Returns:
            Dict with success status and ERP's response ID
        """
        pass
    
    def transform_data(self, our_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform our data format to ERP's format.
        
        Override this method for ERP-specific transformations.
        Default implementation returns data as-is.
        
        Args:
            our_data: Our standard parsed report data
            
        Returns:
            ERP-formatted data
        """
        return our_data


class ERPError(Exception):
    """Base exception for ERP errors."""
    pass


class AuthenticationError(ERPError):
    """Raised when ERP authentication fails."""
    pass


class ConnectionError(ERPError):
    """Raised when ERP connection fails."""
    pass


class SyncError(ERPError):
    """Raised when data sync to ERP fails."""
    pass
