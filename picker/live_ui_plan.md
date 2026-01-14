# Live UI Plan for Picker Project

## Objective

Create a responsive, visually clear, and slightly artistic/technical web page served at `/` by the picker application. The page will display:
- The live MJPEG stream from the camera
- The latest captured still image (when available)
- The latest generated image (img2img output, when available)
- Placeholders for still/gen images when not available

The page must:
- Fit and scale to the available window size on a 1024x600 (landscape) HDMI LCD, accounting for desktop/window borders
- Use a fixed aspect ratio layout that scales responsively
- Be visually clear, with a technical/artistic style
- Work in Chromium and Firefox

---

## Implementation Steps

### 1. Routing and Server Changes
- Add a `/` route in `StreamingHandler` (picker/capture_still.py) to serve the new HTML page.
- Add routes to serve:
  - `/assets/latest_still.jpg` (latest still image)
  - `/assets/img2img_output.jpg` (latest generated image)
  - `/assets/placeholder_still.jpg` and `/assets/placeholder_gen.jpg` (static placeholders)
  - `/assets/live_still_gen.html` (the new HTML page)

### 2. HTML Page ([picker/assets/live_still_gen.html])
- Use a fixed aspect ratio container (e.g., 1024x600 or 16:9) that scales responsively with CSS:
  - `max-width: 100vw; max-height: 100vh; object-fit: contain;`
- Layout:
  - Prominent live MJPEG stream: `<img src="/stream.mjpg">`
  - Still and gen images side-by-side or below, using `<img src="/assets/latest_still.jpg">` and `<img src="/assets/img2img_output.jpg">`
  - Placeholders for still/gen images when not available
- Use modern CSS (flexbox/grid, custom fonts, color themes) for a technical/artistic look
- Add a `viewport` meta tag for proper scaling
- Optionally, add subtle borders/backgrounds for clarity

### 3. JavaScript Logic
- Poll `/assets/latest_still.jpg` and `/assets/img2img_output.jpg` rapidly (e.g., every 100–200ms)
- When a new still is captured, update the still image instantly and reset the gen image to its placeholder
- When a new gen image is available, update it instantly
- Use cache-busting query parameters (e.g., `?t=timestamp`) to force image refresh

### 4. Image Saving and Asset Management
- Update picker app logic to save still and gen images to `picker/assets/` (not project root)
- Use consistent filenames: `latest_still.jpg`, `img2img_output.jpg`
- Place static placeholder images in `picker/assets/`
- Update any hardcoded references to image paths

### 5. Testing and Tuning
- Test in Chromium and Firefox on the 1024x600 display
- Resize window to ensure the page always fits and remains clear
- Adjust CSS and polling intervals for best user experience

---

## Further Considerations
- All UI elements should scale proportionally for clarity and aesthetics
- Optionally, add subtle animations or SVG overlays for style
- Ensure the server can handle rapid polling efficiently
- Document any new dependencies or configuration changes

---

## Summary
This plan will deliver a responsive, visually appealing, and technically clear web UI for the picker project, optimized for the Raspberry Pi HDMI LCD and ready for further extension.
