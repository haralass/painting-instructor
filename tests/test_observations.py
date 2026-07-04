"""
Unit tests for backend.teaching.observations — the Claude vision call that
grounds a few sentences of teaching text in a job's own analysis data.

No test here makes a real network call: CI never has ANTHROPIC_API_KEY set,
so the "missing key" path is what actually runs in CI, and the "success"
path is exercised against a mocked client.
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from backend.teaching.observations import generate_observations


@pytest.fixture
def reference_image(tmp_path: Path) -> str:
    img = Image.new("RGB", (64, 64), (120, 140, 90))
    path = tmp_path / "reference.jpg"
    img.save(path)
    return str(path)


def _sample_palette() -> list[dict]:
    return [
        {"id": 0, "name": "Blue", "base_rgb": (120, 140, 220), "area_fraction": 0.47},
        {"id": 1, "name": "Green", "base_rgb": (90, 130, 80), "area_fraction": 0.31},
    ]


def _sample_value_zones() -> list[dict]:
    return [
        {"id": 0, "label": "shadow", "grey_value": 40},
        {"id": 1, "label": "midtone", "grey_value": 128},
        {"id": 2, "label": "highlight", "grey_value": 220},
    ]


class TestNoApiKey:
    def test_returns_none_without_api_key(self, reference_image: str, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = generate_observations(
            reference_path=reference_image,
            medium="oil",
            medium_cfg={"name": "Oil Paint"},
            palette=_sample_palette(),
            value_zone_list=_sample_value_zones(),
            region_count=12,
        )
        assert result is None

    def test_never_raises_without_api_key(self, reference_image: str, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Should short-circuit before ever touching the network or the file.
        generate_observations(
            reference_path="/nonexistent/path.jpg",
            medium="oil",
            medium_cfg={"name": "Oil Paint"},
            palette=[],
            value_zone_list=[],
            region_count=0,
        )


class TestMissingReferenceFile:
    def test_returns_none_for_missing_file(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        result = generate_observations(
            reference_path="/nonexistent/path.jpg",
            medium="oil",
            medium_cfg={"name": "Oil Paint"},
            palette=_sample_palette(),
            value_zone_list=_sample_value_zones(),
            region_count=12,
        )
        assert result is None


class TestMockedSuccess:
    def test_returns_text_from_mocked_client(self, reference_image: str, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Your sky dominates the frame — block that cool blue mass first."
        mock_message = MagicMock(content=[text_block])

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch("anthropic.Anthropic", return_value=mock_client) as mock_ctor:
            result = generate_observations(
                reference_path=reference_image,
                medium="oil",
                medium_cfg={"name": "Oil Paint"},
                palette=_sample_palette(),
                value_zone_list=_sample_value_zones(),
                region_count=12,
            )

        assert result == "Your sky dominates the frame — block that cool blue mass first."
        mock_ctor.assert_called_once_with(api_key="sk-test-key")
        # The prompt should be grounded in the real per-job data, not generic text.
        _, kwargs = mock_client.messages.create.call_args
        user_content = kwargs["messages"][0]["content"]
        prompt_text = next(b["text"] for b in user_content if b["type"] == "text")
        assert "Blue (47%)" in prompt_text
        assert "shadow, midtone, highlight" in prompt_text
        assert "12 distinct regions" in prompt_text

    def test_returns_none_on_client_exception(self, reference_image: str, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API down")

        with patch("anthropic.Anthropic", return_value=mock_client):
            result = generate_observations(
                reference_path=reference_image,
                medium="oil",
                medium_cfg={"name": "Oil Paint"},
                palette=_sample_palette(),
                value_zone_list=_sample_value_zones(),
                region_count=12,
            )

        assert result is None
