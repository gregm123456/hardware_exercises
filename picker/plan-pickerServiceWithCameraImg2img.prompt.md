## Updated Plan: Picker Camera Still Service with Fallback

**Implementation Status: COMPLETED**

This plan describes how to implement an alternate picker systemd service (`picker_camera_still_startup.service`) and a revamped picker application that supports both txt2img and img2img modes, with fallback logic if camera capture fails.

### Steps
1. Create a new systemd service file `picker_camera_still_startup.service` (based on the original, but passes a CLI flag to select img2img mode).
2. Update the picker application (or add a CLI flag, e.g., `--img2img-mode` or `--generation-mode [txt2img|img2img]`) to:
    - On "GO" button press, attempt to invoke `capture_still.py` to save a 512x512 PNG (e.g., `still.png`).
    - If image capture succeeds, base64-encode the image and POST to the `/generate` endpoint with `mode: img2img`, the prompt, and the base64 image.
    - If image capture fails (timeout, error, or missing file), fall back to the standard txt2img call (prompt only, no image).
3. All endpoint addresses, prompts, and button logic remain unchanged.
4. Image capture should be blocking (synchronous) to ensure the latest image is used for img2img.

### Fallback Logic
- If `capture_still.py` fails or does not produce a valid image in a reasonable time, log the error and proceed with a txt2img request as a fallback.


### Compatibility Requirement (Explicit)
- The revamped picker application **must default to txt2img mode if no new CLI flag is provided**. This ensures that the existing `picker_startup.service` will continue to work without modification and will not break against the new code. Only the new service will use the img2img mode via the explicit flag.

### Service Exclusivity Note
- **Only one picker service (either the original or the camera-still version) should be enabled and running at a time.** These services are mutually exclusive and should not be run simultaneously.

### Further Considerations
- The new service can be enabled/disabled independently of the original picker service.
- The CLI flag should be documented and supported in the picker application's help output.
- Error handling and logging should clearly indicate when a fallback to txt2img occurs.
