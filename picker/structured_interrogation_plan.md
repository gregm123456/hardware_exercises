# Plan: Add Structured Image Interrogation

Classification of the captured still image will be added using categories derived from knob configurations. This classification will happen immediately after capture and before the image generation request, with results displayed in a new UI section.

## Implementation Steps

### 1. SD Client Extension ([picker/sd_client.py](picker/sd_client.py))
- Implement `interrogate_structured(image_b64, categories)` method.
- This will `POST` to `/sdapi/v1/interrogate/structured` with the provided image and categories.
- Returns the parsed JSON response (containing "results" and "general_tags").

### 2. Core State Management ([picker/core.py](picker/core.py))
- Initialize `self.last_interrogate = None` in `PickerCore.__init__`.
- Update the `_bg_generate` function:
    - Immediately after capturing and encoding the `init_image` (base64 string), extract categories from `self.texts`.
    - Build the `categories` dict: `{"Category Title": ["non", "empty", "values"]}`.
    - Call `sd_client.interrogate_structured(init_image, categories)`.
    - Store the result in `self.last_interrogate`.

### 3. API Status Update ([picker/capture_still.py](picker/capture_still.py))
- Update `StreamingHandler.send_json_status()` to include the `interrogation_results` field, populated from `self.server.core.last_interrogate`.

### 4. Web UI Enhancements ([picker/assets/live_still_gen.html](picker/assets/live_still_gen.html))
- **HTML**: Add a new `.panel.interrogation-results` div between the main image panels and the prompt box.
- **CSS**: Ensure the new panel matches the existing technical/artistic style.
- **JavaScript**:
    - Add `const interrogationContent = document.getElementById('interrogation-content')`.
    - In `pollStatus()`, check for `data.interrogation_results`.
    - If present, format the `results` object into a list of strings: `Winner: Confidence%`.
    - Display the formatted list and any `general_tags`.

## Flow Sequence (on GO button press)
1. Capture high-res still image from camera.
2. Base64 encode the image.
3. **NEW**: Perform structured interrogation using knob-derived categories.
4. Update `last_interrogate` state (immediately visible to UI polling).
5. Proceed with `generate_image` (img2img) as before.
6. Display final generated image on e-paper and UI.
