"""Tests for model cost lookup functionality."""

import pytest

from app.model_costs import get_model_cost, get_model_cost_info, normalize_model_name


class TestNormalizeModelName:
    """Test model name normalization."""

    def test_claude_3_5_pattern(self):
        """Test claude-X-Y-family-date pattern."""
        assert normalize_model_name("claude-3-5-haiku-20241022") == "haiku-3.5"
        assert normalize_model_name("claude-3-5-sonnet-20241022") == "sonnet-3.5"

    def test_claude_3_pattern(self):
        """Test claude-X-family-date pattern."""
        assert normalize_model_name("claude-3-opus-20240229") == "opus-3"
        assert normalize_model_name("claude-3-haiku-20240307") == "haiku-3"

    def test_claude_family_version_pattern(self):
        """Test claude-family-X-Y pattern."""
        assert normalize_model_name("claude-sonnet-4-0") == "sonnet-4"
        assert normalize_model_name("claude-opus-4-0") == "opus-4"
        assert normalize_model_name("claude-sonnet-3-7") == "sonnet-3.7"

    def test_claude_family_major_pattern(self):
        """Test claude-family-X pattern."""
        assert normalize_model_name("claude-opus-4") == "opus-4"
        assert normalize_model_name("claude-haiku-3") == "haiku-3"

    def test_case_insensitive(self):
        """Test that normalization is case-insensitive."""
        assert normalize_model_name("Claude-3-5-Haiku-20241022") == "haiku-3.5"
        assert normalize_model_name("CLAUDE-OPUS-4") == "opus-4"

    def test_invalid_model_name(self):
        """Test that invalid model names raise ValueError."""
        with pytest.raises(ValueError, match="Unable to parse model name"):
            normalize_model_name("gpt-4")
        with pytest.raises(ValueError, match="Unable to parse model name"):
            normalize_model_name("claude-unknown-model")

    def test_fallback_pattern_specificity(self):
        """Test that fallback pattern doesn't match unintended numbers."""
        # Should match the version after the family name
        assert normalize_model_name("claude-haiku-3-something-20241022") == "haiku-3"

        # Should not match random numbers that aren't version numbers
        with pytest.raises(ValueError, match="Unable to parse model name"):
            normalize_model_name("claude-12345-haiku")


class TestGetModelCost:
    """Test model cost lookup."""

    def test_haiku_3_5_cost(self):
        """Test Claude 3.5 Haiku costs."""
        input_cost, output_cost = get_model_cost("claude-3-5-haiku-20241022")
        assert input_cost == 0.80 / 1_000_000  # $0.80 per million
        assert output_cost == 4.0 / 1_000_000  # $4.00 per million

    def test_sonnet_3_5_cost(self):
        """Test Claude 3.5 Sonnet costs."""
        input_cost, output_cost = get_model_cost("claude-3-5-sonnet-20241022")
        assert input_cost == 3.0 / 1_000_000  # $3 per million
        assert output_cost == 15.0 / 1_000_000  # $15 per million

    def test_opus_3_cost(self):
        """Test Claude 3 Opus costs."""
        input_cost, output_cost = get_model_cost("claude-3-opus-20240229")
        assert input_cost == 15.0 / 1_000_000  # $15 per million
        assert output_cost == 75.0 / 1_000_000  # $75 per million

    def test_haiku_3_cost(self):
        """Test Claude 3 Haiku costs."""
        input_cost, output_cost = get_model_cost("claude-3-haiku-20240307")
        assert input_cost == 0.25 / 1_000_000  # $0.25 per million
        assert output_cost == 1.25 / 1_000_000  # $1.25 per million

    def test_sonnet_4_cost(self):
        """Test Claude 4 Sonnet costs."""
        input_cost, output_cost = get_model_cost("claude-sonnet-4-0")
        assert input_cost == 3.0 / 1_000_000  # $3 per million
        assert output_cost == 15.0 / 1_000_000  # $15 per million

    def test_opus_4_cost(self):
        """Test Claude 4 Opus costs."""
        input_cost, output_cost = get_model_cost("claude-opus-4-0")
        assert input_cost == 15.0 / 1_000_000  # $15 per million
        assert output_cost == 75.0 / 1_000_000  # $75 per million

    def test_unknown_model(self):
        """Test that unknown models raise ValueError."""
        with pytest.raises(ValueError, match="Model family .* not found"):
            get_model_cost("claude-unknown-1-0")


class TestGetModelCostInfo:
    """Test get_model_cost_info function."""

    def test_returns_dict_format(self):
        """Test that the function returns the expected dictionary format."""
        info = get_model_cost_info("claude-3-5-haiku-20241022")
        assert isinstance(info, dict)
        assert "per_input_token" in info
        assert "per_output_token" in info
        assert info["per_input_token"] == 0.80 / 1_000_000
        assert info["per_output_token"] == 4.0 / 1_000_000

    def test_different_models(self):
        """Test various model cost lookups."""
        # Test a few different models
        opus_info = get_model_cost_info("claude-opus-4")
        assert opus_info["per_input_token"] == 15.0 / 1_000_000
        assert opus_info["per_output_token"] == 75.0 / 1_000_000

        haiku3_info = get_model_cost_info("claude-3-haiku-20240307")
        assert haiku3_info["per_input_token"] == 0.25 / 1_000_000
        assert haiku3_info["per_output_token"] == 1.25 / 1_000_000
