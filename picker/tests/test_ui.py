from picker.ui import compose_overlay


def test_compose_overlay_basic():
    title = "Category"
    values = [f"V{i}" for i in range(12)]
    img = compose_overlay(title, values, selected_index=2, full_screen=(400, 300))
    assert img.size == (400, 300)
    # ensure selected area is darker than background at a sampled pixel
    px = img.getpixel((10, 200))
    assert px < 255


if __name__ == "__main__":
    test_compose_overlay_basic()
    print("UI OK")
