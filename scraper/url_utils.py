import hashlib
from urllib.parse import urlparse, urldefrag, urljoin

class URLUtils:
    """Utilities for URL normalization and manipulation."""
    
    @staticmethod
    def normalize(url: str) -> str:
        """
        Normalize URL for consistent comparison.
        
        - Remove fragments
        - Remove trailing slashes
        - Lowercase scheme and domain
        """
        # Remove fragment
        url, _ = urldefrag(url)
        
        # Parse URL
        parsed = urlparse(url)
        
        # Normalize components
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path
        
        # Reconstruct
        normalized = f"{scheme}://{netloc}{path}"
        
        if parsed.query:
            normalized += f"?{parsed.query}"
            
        return normalized
    
    @staticmethod
    def get_hash(url: str) -> str:
        """
        Generate SHA256 hash of normalized URL.
        
        Args:
            url: URL to hash
            
        Returns:
            Hex digest of hash
        """
        normalized = URLUtils.normalize(url)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    
    @staticmethod
    def get_domain(url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc
    
    @staticmethod
    def same_domain(url1: str, url2: str) -> bool:
        """Check if two URLs are from the same domain."""
        return URLUtils.get_domain(url1) == URLUtils.get_domain(url2)
    
    @staticmethod
    def is_valid_http_url(url: str) -> bool:
        """Check if URL is a valid HTTP/HTTPS URL."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except:
            return False

