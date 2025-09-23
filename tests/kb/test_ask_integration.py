"""Integration test for KB in ask command flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Adventorator.commands.ask import ask_cmd


@pytest.fixture
def mock_invocation():
    """Create a mock invocation with necessary attributes."""
    inv = AsyncMock()
    inv.user_id = 12345
    inv.responder = AsyncMock()
    inv.responder.send = AsyncMock()
    
    # Mock settings with feature flags enabled
    settings = MagicMock()
    settings.features_improbability_drive = True
    settings.features_ask = True
    settings.features_ask_nlu_rule_based = True
    settings.features_ask_kb_lookup = True
    settings.features_ask_nlu_debug = True
    
    # Mock KB config
    kb_config = MagicMock()
    kb_config.timeout_s = 0.05
    kb_config.max_candidates = 5
    kb_config.cache_ttl_s = 60.0
    kb_config.cache_max_size = 1024
    kb_config.max_terms_per_call = 20
    settings.ask_kb = kb_config
    
    inv.settings = settings
    return inv


@pytest.fixture
def mock_opts():
    """Create mock ask options."""
    opts = MagicMock()
    opts.message = "attack the goblin"
    return opts


@pytest.mark.asyncio
async def test_ask_command_with_kb_disabled(mock_invocation, mock_opts):
    """Test ask command when KB is disabled."""
    # Disable KB lookup
    mock_invocation.settings.features_ask_kb_lookup = False
    
    with patch('Adventorator.commands.ask.parse_and_tag') as mock_parse, \
        patch('Adventorator.commands.ask.log_event') as _mock_log:
        
        # Mock NLU response
        mock_intent = MagicMock()
        mock_intent.action = "attack"
        mock_intent.target_ref = "goblin"
        mock_intent.modifiers = []
        mock_parse.return_value = (mock_intent, [])
        
        await ask_cmd(mock_invocation, mock_opts)
        
        # Verify no KB-related imports or calls
        mock_invocation.responder.send.assert_called()
        # Should have normal ask response without KB info
        call_args = mock_invocation.responder.send.call_args_list
        summary_call = [call for call in call_args if "Interpreted intent" in str(call)]
        assert len(summary_call) > 0


@pytest.mark.asyncio 
async def test_ask_command_with_kb_enabled(mock_invocation, mock_opts):
    """Test ask command when KB is enabled."""
    with patch('Adventorator.commands.ask.parse_and_tag') as mock_parse, \
        patch('Adventorator.commands.ask.log_event') as mock_log, \
         patch('Adventorator.commands.ask.get_kb_adapter') as mock_get_adapter:
        
        # Mock NLU response with entity
        mock_intent = MagicMock()
        mock_intent.action = "attack"
        mock_intent.target_ref = "goblin"
        mock_intent.modifiers = []
        
        mock_tag = MagicMock()
        mock_tag.key = "entity.target"
        mock_tag.value = "goblin"
        mock_parse.return_value = (mock_intent, [mock_tag])
        
        # Mock KB adapter
        mock_adapter = AsyncMock()
        mock_resolution = MagicMock()
        mock_resolution.canonical_id = "character:1"
        mock_resolution.candidates = []
        mock_resolution.reason = "Exact match found"
        mock_adapter.bulk_resolve.return_value = [mock_resolution]
        mock_get_adapter.return_value = mock_adapter
        
        await ask_cmd(mock_invocation, mock_opts)
        
        # Verify KB adapter was called
        mock_get_adapter.assert_called_once()
        mock_adapter.bulk_resolve.assert_called_once()
        
        # Verify KB lookup was logged
        kb_log_calls = [
            call for call in mock_log.call_args_list
            if len(call[0]) > 1 and call[0][1] == "kb_lookup"
        ]
        assert len(kb_log_calls) > 0


@pytest.mark.asyncio
async def test_ask_command_kb_error_handling(mock_invocation, mock_opts):
    """Test ask command gracefully handles KB errors."""
    with patch('Adventorator.commands.ask.parse_and_tag') as mock_parse, \
        patch('Adventorator.commands.ask.log_event') as _mock_log, \
         patch('Adventorator.commands.ask.get_kb_adapter') as mock_get_adapter:
        
        # Mock NLU response
        mock_intent = MagicMock()
        mock_intent.action = "attack"
        mock_intent.target_ref = "goblin"
        mock_intent.modifiers = []
        mock_parse.return_value = (mock_intent, [])
        
        # Mock KB adapter that raises exception
        mock_get_adapter.side_effect = Exception("KB error")
        
        # Should not raise exception - should handle gracefully
        await ask_cmd(mock_invocation, mock_opts)
        
        # Verify normal response was sent despite KB error
        mock_invocation.responder.send.assert_called()


@pytest.mark.asyncio
async def test_ask_command_empty_message(mock_invocation):
    """Test ask command with empty message."""
    opts = MagicMock()
    opts.message = ""
    
    await ask_cmd(mock_invocation, opts)
    
    # Should send error message for empty input
    mock_invocation.responder.send.assert_called_with(
        "❌ You need to provide a message.", 
        ephemeral=True
    )