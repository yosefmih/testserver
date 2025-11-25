from bs4 import BeautifulSoup
import re

class TextProcessor:
    """Extract clean text from HTML content."""
    
    # Tags to remove completely
    REMOVE_TAGS = ['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript']
    
    def __init__(self):
        self.soup = None
    
    def extract_text(self, html_content: str) -> str:
        """
        Extract clean text from HTML.
        
        Args:
            html_content: Raw HTML string
            
        Returns:
            Cleaned text content
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.debug(f"Parsing HTML ({len(html_content)} bytes)")
            
            # Parse HTML
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Remove unwanted tags
            tags_removed = 0
            for tag in self.REMOVE_TAGS:
                elements = soup.find_all(tag)
                if elements:
                    logger.debug(f"Removing {len(elements)} <{tag}> elements")
                    for element in elements:
                        element.decompose()
                    tags_removed += len(elements)
            
            logger.debug(f"Removed {tags_removed} unwanted elements")
            
            # Get text
            text = soup.get_text(separator='\n', strip=True)
            logger.debug(f"Extracted text: {len(text)} characters (before cleaning)")
            
            # Clean up whitespace
            text = self._clean_whitespace(text)
            logger.debug(f"After whitespace cleanup: {len(text)} characters")
            
            return text
            
        except Exception as e:
            logger.warning(f"BeautifulSoup parsing failed ({type(e).__name__}), using fallback")
            # Fallback to simple text extraction
            return self._simple_text_extract(html_content)
    
    def extract_title(self, html_content: str) -> str:
        """Extract page title from HTML."""
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            title_tag = soup.find('title')
            return title_tag.get_text(strip=True) if title_tag else ''
        except:
            return ''
    
    def _clean_whitespace(self, text: str) -> str:
        """Clean up excessive whitespace."""
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        
        # Replace multiple newlines with double newline
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        
        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    def _simple_text_extract(self, html_content: str) -> str:
        """Fallback simple text extraction."""
        # Remove script and style tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        
        return self._clean_whitespace(text)

