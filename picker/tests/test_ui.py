from picker.ui import compose_overlay


def test_compose_overlay_basic():
    title = "Category"
    values = [f"V{i}" for i in range(12)]
    img = compose_overlay(title, values, selected_index=2, full_screen=(400, 300))
    assert img.size == (400, 300)
    # ensure selected area is darker than background at a sampled pixel inside the selected item
    # Compute a y coordinate inside the selected item (approx)
    margin = 16
    font_h = 28
    y_start = margin + font_h + 8
    item_h = (300 - y_start - margin) // 12
    sample_y = y_start + 2 * item_h + item_h // 2
    px = img.getpixel((10, sample_y))
    assert px < 255


if __name__ == "__main__":
    test_compose_overlay_basic()
    print("UI OK")
