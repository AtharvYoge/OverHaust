"""
Tests for token estimation utilities.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from packages.tokenization.token_estimator import estimate_tokens, estimate_reduction, TokenEstimator


def test_basic_token_estimation():
    """Test basic token estimation functionality."""
    text = "Hello, world! This is a test."
    tokens = estimate_tokens(text)
    assert isinstance(tokens, int)
    assert tokens > 0
    print(f"✓ Basic token estimation: '{text}' -> {tokens} tokens")


def test_different_models():
    """Test token estimation with different models."""
    text = "This is a test sentence for token estimation."
    
    gpt4_tokens = estimate_tokens(text, "gpt-4")
    gpt35_tokens = estimate_tokens(text, "gpt-3.5-turbo")
    
    print(f"✓ GPT-4 tokens: {gpt4_tokens}")
    print(f"✓ GPT-3.5 tokens: {gpt35_tokens}")
    
    # Both should be positive integers
    assert gpt4_tokens > 0
    assert gpt35_tokens > 0


def test_token_reduction_estimation():
    """Test token reduction estimation."""
    original = "This is a very long sentence that contains lots of information that might not be necessary for the AI to process. " * 10
    optimized = "This is a test sentence."
    
    reduction = estimate_reduction(original, optimized)
    
    assert "original_tokens" in reduction
    assert "optimized_tokens" in reduction
    assert "saved_tokens" in reduction
    assert "reduction_percent" in reduction
    
    assert reduction["original_tokens"] > reduction["optimized_tokens"]
    assert reduction["saved_tokens"] > 0
    assert reduction["reduction_percent"] > 0
    
    print(f"✓ Token reduction: {reduction['original_tokens']} -> {reduction['optimized_tokens']} "
          f"(-{reduction['saved_tokens']} tokens, {reduction['reduction_percent']}%)")


def test_token_estimator_class():
    """Test the TokenEstimator class directly."""
    estimator = TokenEstimator(default_model="gpt-4")
    
    text = "Testing the TokenEstimator class."
    tokens = estimator.estimate_tokens(text)
    
    assert isinstance(tokens, int)
    assert tokens > 0
    print(f"✓ TokenEstimator class: {tokens} tokens")


if __name__ == "__main__":
    print("Running token estimation tests...\n")
    
    test_basic_token_estimation()
    test_different_models()
    test_token_reduction_estimation()
    test_token_estimator_class()
    
    print("\n✓ All token estimation tests passed!")