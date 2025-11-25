from bs4 import BeautifulSoup
import re

class TextProcessor:
    """Extract clean text from HTML content."""
    
    # Tags to remove completely (keep it minimal to avoid removing content)
    REMOVE_TAGS = ['script', 'style', 'noscript']
    
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
            
            # Get initial text count before any removal
            initial_text = soup.get_text(strip=True)
            logger.debug(f"Initial text (before cleanup): {len(initial_text)} chars")
            
            # Remove unwanted tags
            tags_removed = 0
            for tag in self.REMOVE_TAGS:
                elements = soup.find_all(tag)
                if elements:
                    logger.debug(f"Removing {len(elements)} <{tag}> elements")
                    for element in elements:
                        element.decompose()
                    tags_removed += len(elements)
            
            logger.debug(f"Removed {tags_removed} unwanted tag elements")
            
            # DON'T remove elements by class - too aggressive!
            # Many sites use these class names legitimately for content
            # Only remove unwanted TAGS, not classes
            
            # Try to find main content area first (prioritize semantic HTML)
            main_content = None
            content_selectors = [
                ('article', soup.find('article')),
                ('main', soup.find('main')),
                ('role=main', soup.find(attrs={'role': 'main'})),
                ('div.content', soup.find('div', {'class': re.compile(r'(^|\\s)(content|article|post-content|entry-content|main-content)(\\s|$)', re.I)})),
                ('div#content', soup.find('div', {'id': re.compile(r'(content|article|post|entry|main)', re.I)})),
                ('div.post', soup.find('div', {'class': re.compile(r'(^|\\s)(post|entry)(\\s|$)', re.I)})),
            ]
            
            for selector_name, selector in content_selectors:
                if selector:
                    content_text = selector.get_text(strip=True)
                    if content_text and len(content_text) > 200:  # Ensure meaningful content
                        main_content = selector
                        logger.debug(f"Found main content area: {selector_name} ({len(content_text)} chars)")
                        break
            
            # Use main content if found, otherwise use whole page
            extract_from = main_content if main_content else soup
            
            if main_content:
                logger.info(f"✅ Extracting from main content area")
            else:
                logger.info(f"⚠️  No main content area found, using full page")
            
            # Get text
            text = extract_from.get_text(separator='\n', strip=True)
            logger.info(f"Extracted text: {len(text)} characters (before whitespace cleanup)")
            
            # Clean up whitespace
            text = self._clean_whitespace(text)
            logger.info(f"After whitespace cleanup: {len(text)} characters")
            
            # Log sample of extracted text
            if text:
                preview = text[:300].replace('\n', ' ')
                logger.info(f"Text preview: {preview}...")
            else:
                logger.warning(f"⚠️  No text extracted! This might be a JavaScript-rendered page")
            
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

