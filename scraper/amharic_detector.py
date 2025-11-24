import re
from typing import Tuple, Dict

class AmharicDetector:
    """
    Detects Amharic text using Unicode Ethiopic script range.
    Ethiopic Unicode block: U+1200 to U+137F (core Ethiopic)
    Extended: U+1380 to U+139F (Ethiopic Supplement)
    U+2D80 to U+2DDF (Ethiopic Extended)
    """
    
    # Core Ethiopic script pattern
    ETHIOPIC_PATTERN = re.compile(r'[\u1200-\u137F\u1380-\u139F\u2D80-\u2DDF]+')
    
    def __init__(self, threshold: float = 0.3):
        """
        Initialize detector.
        
        Args:
            threshold: Minimum percentage of Ethiopic characters to consider text as Amharic
        """
        self.threshold = threshold
    
    def detect(self, text: str, threshold: float = None) -> Tuple[bool, float, Dict]:
        """
        Detect if text contains Amharic.
        
        Args:
            text: Text to analyze
            threshold: Override default threshold
            
        Returns:
            Tuple of (is_amharic, amharic_percentage, stats)
        """
        if threshold is None:
            threshold = self.threshold
            
        if not text or len(text) == 0:
            return False, 0.0, {'total_chars': 0, 'amharic_chars': 0, 'non_whitespace': 0}
        
        # Count Amharic characters
        amharic_matches = self.ETHIOPIC_PATTERN.findall(text)
        amharic_chars = len(''.join(amharic_matches))
        
        # Calculate percentage (excluding whitespace)
        total_chars = len(text)
        non_whitespace = len(text.replace(' ', '').replace('\n', '').replace('\t', '').replace('\r', ''))
        
        if non_whitespace == 0:
            return False, 0.0, {'total_chars': total_chars, 'amharic_chars': 0, 'non_whitespace': 0}
        
        percentage = amharic_chars / non_whitespace
        is_amharic = percentage >= threshold
        
        stats = {
            'total_chars': total_chars,
            'amharic_chars': amharic_chars,
            'non_whitespace': non_whitespace,
            'percentage': percentage,
            'threshold_used': threshold
        }
        
        return is_amharic, percentage, stats
    
    def extract_amharic_text(self, text: str) -> str:
        """
        Extract only Amharic portions of text.
        
        Args:
            text: Text containing mixed content
            
        Returns:
            String with only Amharic text
        """
        amharic_parts = self.ETHIOPIC_PATTERN.findall(text)
        return ' '.join(amharic_parts)
    
    def count_amharic_words(self, text: str) -> int:
        """
        Count Amharic 'words' (sequences of Ethiopic characters).
        
        Args:
            text: Text to analyze
            
        Returns:
            Number of Amharic word sequences
        """
        return len(self.ETHIOPIC_PATTERN.findall(text))

