"""
Token estimation utilities for Overhaust.
Provides abstractions for estimating token usage across different AI models.
"""

import tiktoken
from typing import Dict, Union, Optional
from enum import Enum


class ModelProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


class TokenEstimator:
    """Estimates token usage for various AI models."""
    
    # Model to encoder mapping for OpenAI-compatible models
    MODEL_ENCODERS = {
        # OpenAI models
        "gpt-4": "cl100k_base",
        "gpt-4-turbo": "cl100k_base",
        "gpt-4o": "cl100k_base",
        "gpt-3.5-turbo": "cl100k_base",
        "gpt-3.5-turbo-16k": "cl100k_base",
        
        # For other models, we'll use cl100k_base as a reasonable approximation
        # In production, we'd want model-specific encoders
    }
    
    def __init__(self, default_model: str = "gpt-4"):
        self.default_model = default_model
        self._encoders: Dict[str, tiktoken.Encoding] = {}
    
    def _get_encoder(self, model: str) -> tiktoken.Encoding:
        """Get or create tokenizer encoder for a model."""
        if model not in self._encoders:
            encoding_name = self.MODEL_ENCODERS.get(model, "cl100k_base")
            self._encoders[model] = tiktoken.get_encoding(encoding_name)
        return self._encoders[model]
    
    def estimate_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Estimate token count for given text using specified model.
        
        Args:
            text: Text to estimate tokens for
            model: Model name (defaults to self.default_model)
            
        Returns:
            Estimated token count
        """
        model = model or self.default_model
        encoder = self._get_encoder(model)
        return len(encoder.encode(text))
    
    def estimate_messages_tokens(self, messages: list, model: Optional[str] = None) -> int:
        """
        Estimate token count for a list of messages (like in chat completions).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name
            
        Returns:
            Estimated token count
        """
        model = model or self.default_model
        encoder = self._get_encoder(model)
        
        tokens_per_message = 3  # Every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = 1     # If there's a name, the role is omitted
        
        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message
            for key, value in message.items():
                num_tokens += len(encoder.encode(value))
                if key == "name":
                    num_tokens += tokens_per_name
        num_tokens += 3  # Every reply is primed with <|start|>assistant<|message|>
        return num_tokens
    
    def estimate_reduction(self, original_text: str, optimized_text: str, 
                          model: Optional[str] = None) -> Dict[str, Union[int, float]]:
        """
        Calculate token reduction between original and optimized text.
        
        Args:
            original_text: Original text
            optimized_text: Optimized/reduced text
            model: Model name for estimation
            
        Returns:
            Dictionary with original, optimized, saved tokens and percentage
        """
        original_tokens = self.estimate_tokens(original_text, model)
        optimized_tokens = self.estimate_tokens(optimized_text, model)
        saved_tokens = original_tokens - optimized_tokens
        reduction_percent = (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0
        
        return {
            "original_tokens": original_tokens,
            "optimized_tokens": optimized_tokens,
            "saved_tokens": saved_tokens,
            "reduction_percent": round(reduction_percent, 2)
        }


# Global estimator instance for convenience
token_estimator = TokenEstimator()


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """Convenience function for token estimation."""
    return token_estimator.estimate_tokens(text, model)


def estimate_reduction(original: str, optimized: str, model: str = "gpt-4") -> Dict[str, Union[int, float]]:
    """Convenience function for token reduction estimation."""
    return token_estimator.estimate_reduction(original, optimized, model)