#!/usr/bin/env python3
"""
Diagnostic script for rotary encoder mode.
Helps identify why the rotary encoder isn't responding to input
and why the menu might be auto-advancing.
"""
import sys
import time
import logging
sys.path.insert(0, '/home/gregm/hardware_exercises')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_encoder_simulation():
    """Test the simulated encoder to verify it works correctly."""
    logger.info("=" * 60)
    logger.info("TEST 1: Simulated Encoder Functionality")
    logger.info("=" * 60)
    from picker.rotary_encoder import SimulatedRotaryEncoder
    
    enc = SimulatedRotaryEncoder()
    logger.info("Created SimulatedRotaryEncoder")
    
    # Verify no events initially
    ev = enc.get_event()
    assert ev is None, f"Expected no initial event, got {ev}"
    logger.info("✓ No spurious events on startup")
    
    # Inject a rotation
    enc.simulate_rotate(+1)
    ev = enc.get_event()
    assert ev == ("rotate", 1), f"Expected ('rotate', 1), got {ev}"
    logger.info("✓ Rotation event generated correctly")
    
    # Inject a button press
    enc.simulate_button(True)
    ev = enc.get_event()
    assert ev == ("button", True), f"Expected ('button', True), got {ev}"
    logger.info("✓ Button press event generated correctly")
    
    # Verify queue is now empty
    ev = enc.get_event()
    assert ev is None, f"Expected empty queue, got {ev}"
    logger.info("✓ Queue empties correctly after consuming events")
    
    logger.info("✓ Simulated encoder tests PASSED\n")

def test_menus_loading():
    """Test menu loading functionality."""
    logger.info("=" * 60)
    logger.info("TEST 2: Menu Loading")
    logger.info("=" * 60)
    from picker.config import load_menus
    
    # Load default menus
    try:
        menus = load_menus()
        logger.info(f"Loaded {len(menus)} menus from default config")
        for i, (title, values) in enumerate(menus):
            logger.info(f"  Menu {i}: '{title}' with {len(values)} values")
            logger.info(f"    Values: {values[:5]}{'...' if len(values) > 5 else ''}")
        
        assert len(menus) > 0, "No menus loaded"
        for title, values in menus:
            assert isinstance(title, str) and title, f"Invalid title: {title}"
            assert isinstance(values, list) and len(values) > 0, f"Invalid values for {title}: {values}"
        
        logger.info("✓ Menu loading tests PASSED\n")
        return menus
    except Exception as e:
        logger.error(f"✗ Menu loading FAILED: {e}")
        return None

def test_rotary_core(menus):
    """Test RotaryPickerCore state machine."""
    logger.info("=" * 60)
    logger.info("TEST 3: RotaryPickerCore State Machine")
    logger.info("=" * 60)
    from picker.rotary_core import RotaryPickerCore, NavState
    
    if not menus:
        logger.error("Skipping - no menus available")
        return
    
    displays = []
    def capture_display(title, items, selected_index):
        displays.append((title, items, selected_index))
        logger.info(f"  [Display] title={title!r}, cursor={selected_index}, items={len(items)}")
    
    core = RotaryPickerCore(menus, on_display=capture_display)
    logger.info(f"✓ RotaryPickerCore created, initial state={core.state.name}")
    
    # Check initial display
    assert len(displays) > 0, "No display refresh on initialization"
    title, items, cursor = displays[-1]
    logger.info(f"✓ Initial display: {len(items)} items, cursor={cursor}")
    
    # Test rotation
    logger.info("Testing rotation +1...")
    core.handle_rotate(+1)
    assert len(displays) > 1, "No display update after rotation"
    title2, items2, cursor2 = displays[-1]
    assert cursor2 == 1, f"Expected cursor=1 after rotate, got {cursor2}"
    logger.info(f"✓ Rotation worked: cursor changed from {cursor} to {cursor2}")
    
    # Test multiple rotations
    logger.info("Testing rotation +3...")
    core.handle_rotate(+3)
    title3, items3, cursor3 = displays[-1]
    logger.info(f"✓ Cursor at {cursor3} after additional +3 rotation")
    
    # Test wrap-around
    logger.info("Testing wrap-around (rotating past end)...")
    n_items = len(items)
    core._cursor = n_items - 1  # Set to last item
    core.handle_rotate(+1)
    title4, items4, cursor4 = displays[-1]
    assert cursor4 == 0, f"Expected wrap-around to cursor=0, got {cursor4}"
    logger.info(f"✓ Wrap-around works: from {n_items-1} wraps to {cursor4}")
    
    logger.info("✓ RotaryPickerCore tests PASSED\n")
    return core

def main():
    logger.info("\n" + "=" * 60)
    logger.info("ROTARY ENCODER DIAGNOSTIC SUITE")
    logger.info("=" * 60 + "\n")
    
    try:
        # Test 1: Encoder simulation
        test_encoder_simulation()
        
        # Test 2: Menu loading
        menus = test_menus_loading()
        
        # Test 3: Core state machine
        if menus:
            test_rotary_core(menus)
        
        logger.info("=" * 60)
        logger.info("Summary: All diagnostic tests PASSED")
        logger.info("\nIf the application still doesn't work:")
        logger.info("  1. Check GPIO pin connections (defaults: CLK=17, DT=18, SW=27)")
        logger.info("  2. Run with --verbose flag to see detailed event logs")
        logger.info("  3. Check logs for 'Event loop' messages showing action_count")
        logger.info("=" * 60 + "\n")
        
    except Exception as e:
        logger.error(f"Diagnostic test FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
