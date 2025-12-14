"""
Pibooth plugin to remove photo background and replace it with a custom background.
Uses rembg for AI-powered background removal.
"""

import os
import io
import logging
import time
from pathlib import Path

import pibooth
from PIL import Image

try:
    from rembg import remove, new_session
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False

__version__ = "1.0.0"

LOGGER = logging.getLogger("pibooth.background_changer")

# Banner visibility settings
BANNER_DISPLAY_TIME = 3.0  # Seconds to show banner before auto-hide
_banner_last_shown = 0  # Timestamp when banner was last triggered
_banner_visible = True  # Whether banner should be visible
_thumbnail_cache = {}  # Cache for background thumbnails

# Touch button areas (will be set by _draw_background_info)
_left_button_rect = None
_right_button_rect = None

# Active background changer instance (for use in hooks)
_active_bg_changer = None

# Section name in pibooth config
SECTION = "BACKGROUND_CHANGER"


def _detect_platform():
    """Detect if running on Raspberry Pi and which model."""
    pi_model = None

    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read()
            if 'Raspberry Pi 5' in model:
                pi_model = 'raspberry_pi_5'
            elif 'Raspberry Pi 4' in model:
                pi_model = 'raspberry_pi_4'
            elif 'Raspberry Pi' in model:
                pi_model = 'raspberry_pi'
    except:
        pass

    if pi_model:
        return pi_model

    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            if 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo:
                return 'raspberry_pi'
    except:
        pass

    return 'desktop'


def _check_vulkan_support():
    """Check if Vulkan is available (for Raspberry Pi GPU acceleration)."""
    try:
        import subprocess
        result = subprocess.run(['vulkaninfo', '--summary'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and 'V3D' in result.stdout:
            LOGGER.info("Vulkan with VideoCore VI (V3D) detected")
            return True
    except:
        pass
    return False


def _get_best_provider():
    """Detect the best available ONNX execution provider.

    Automatically detects and uses the best GPU acceleration available:
    - NVIDIA GPU: CUDA / TensorRT
    - Intel GPU: OpenVINO
    - AMD GPU: ROCm (Linux) / DirectML (Windows)
    - Apple Silicon: CoreML
    - Raspberry Pi: CPU optimized (VideoCore VI not supported by ONNX)
    - Default: CPU
    """
    platform = _detect_platform()
    LOGGER.info("Detected platform: %s", platform)

    # Check for Vulkan on Raspberry Pi (for info only, ONNX doesn't use it)
    if 'raspberry_pi' in platform:
        if _check_vulkan_support():
            LOGGER.info("Note: Vulkan/VideoCore VI detected but not used by ONNX Runtime")
            LOGGER.info("Consider using ncnn with Vulkan for GPU acceleration on Pi")

    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        LOGGER.info("Available ONNX providers: %s", available)

        # Priority order based on typical performance
        # 1. TensorRT (NVIDIA optimized) - fastest
        if 'TensorrtExecutionProvider' in available:
            LOGGER.info("Using TensorRT (NVIDIA optimized) acceleration")
            return ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']

        # 2. CUDA (NVIDIA GPU)
        if 'CUDAExecutionProvider' in available:
            LOGGER.info("Using CUDA (NVIDIA GPU) acceleration")
            return ['CUDAExecutionProvider', 'CPUExecutionProvider']

        # 3. ROCm (AMD GPU on Linux)
        if 'ROCMExecutionProvider' in available:
            LOGGER.info("Using ROCm (AMD GPU) acceleration")
            return ['ROCMExecutionProvider', 'CPUExecutionProvider']

        # 4. OpenVINO (Intel GPU/CPU optimization)
        if 'OpenVINOExecutionProvider' in available:
            LOGGER.info("Using OpenVINO (Intel) acceleration")
            return ['OpenVINOExecutionProvider', 'CPUExecutionProvider']

        # 5. DirectML (Windows GPU - AMD/Intel/NVIDIA)
        if 'DmlExecutionProvider' in available:
            LOGGER.info("Using DirectML (Windows GPU) acceleration")
            return ['DmlExecutionProvider', 'CPUExecutionProvider']

        # 6. CoreML (Apple Silicon)
        if 'CoreMLExecutionProvider' in available:
            LOGGER.info("Using CoreML (Apple Silicon) acceleration")
            return ['CoreMLExecutionProvider', 'CPUExecutionProvider']

        # 7. NNAPI (Android)
        if 'NnapiExecutionProvider' in available:
            LOGGER.info("Using NNAPI (Android) acceleration")
            return ['NnapiExecutionProvider', 'CPUExecutionProvider']

        # 8. ACL (ARM Compute Library - for ARM CPUs like Pi)
        if 'AclExecutionProvider' in available:
            LOGGER.info("Using ACL (ARM Compute Library) acceleration")
            return ['AclExecutionProvider', 'CPUExecutionProvider']

        # Default: CPU with optimization hints
        if 'raspberry_pi' in platform:
            LOGGER.info("Using CPU on Raspberry Pi")
            LOGGER.info("Tip: Using lightweight model 'silueta' for better performance")
        else:
            LOGGER.info("Using CPU (no GPU acceleration available)")

        return ['CPUExecutionProvider']

    except Exception as e:
        LOGGER.warning("Failed to detect ONNX providers: %s", e)
        return None


def _get_recommended_model(platform):
    """Get recommended model based on platform capabilities."""
    if 'raspberry_pi' in platform:
        # Lighter models for Raspberry Pi (CPU)
        # silueta is ~4MB and fast, decent quality for portraits
        return 'silueta'
    else:
        # Better quality for desktop/GPU
        return 'isnet-general-use'


def _get_recommended_resolution(platform):
    """Get recommended image resolution for processing."""
    if 'raspberry_pi' in platform:
        # Lower resolution for faster processing on Pi
        return (640, 480)
    else:
        return (1280, 720)


class BackgroundChanger:
    """Handles background removal and replacement."""

    def __init__(self, backgrounds_dir, model="auto"):
        self.backgrounds_dir = Path(backgrounds_dir)
        self.backgrounds = []
        self.current_index = 0
        self.enabled = True
        self.session = None
        self.providers = None
        self.platform = _detect_platform()

        # Load available backgrounds
        self._load_backgrounds()

        # Detect best execution provider
        self.providers = _get_best_provider()

        # Auto-select model based on platform if set to "auto"
        if model == "auto":
            self.model = _get_recommended_model(self.platform)
            LOGGER.info("Auto-selected model '%s' for platform '%s'", self.model, self.platform)
        else:
            self.model = model

        # Initialize rembg session
        if REMBG_AVAILABLE:
            try:
                # Create session with best available provider
                if self.providers:
                    self.session = new_session(self.model, providers=self.providers)
                else:
                    self.session = new_session(self.model)
                LOGGER.info("Background remover initialized with model: %s", self.model)
            except Exception as e:
                LOGGER.error("Failed to initialize rembg session: %s", e)
                self.enabled = False
        else:
            LOGGER.warning("rembg not installed. Background removal disabled.")
            self.enabled = False

    def _load_backgrounds(self):
        """Load all background images from the backgrounds directory."""
        self.backgrounds = []

        # Add "No background" option as first choice (None represents no background change)
        self.backgrounds.append(None)
        LOGGER.debug("Added 'No background' option as default")

        if not self.backgrounds_dir.exists():
            LOGGER.warning("Backgrounds directory not found: %s", self.backgrounds_dir)
            return

        # Supported image formats
        extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}

        for file in sorted(self.backgrounds_dir.iterdir()):
            if file.suffix.lower() in extensions:
                self.backgrounds.append(file)
                LOGGER.debug("Found background: %s", file.name)

        LOGGER.info("Loaded %d backgrounds from %s (including 'No background' option)",
                   len(self.backgrounds), self.backgrounds_dir)

    def get_current_background(self):
        """Get the currently selected background image."""
        if not self.backgrounds:
            return None
        return self.backgrounds[self.current_index]

    def get_current_background_name(self):
        """Get the name of the current background."""
        bg = self.get_current_background()
        if bg is None:
            return "Sans fond"
        return bg.stem

    def next_background(self):
        """Select the next background."""
        if self.backgrounds:
            self.current_index = (self.current_index + 1) % len(self.backgrounds)
            LOGGER.info("Selected background: %s", self.get_current_background_name())

    def previous_background(self):
        """Select the previous background."""
        if self.backgrounds:
            self.current_index = (self.current_index - 1) % len(self.backgrounds)
            LOGGER.info("Selected background: %s", self.get_current_background_name())

    def toggle_enabled(self):
        """Toggle background replacement on/off."""
        if REMBG_AVAILABLE:
            self.enabled = not self.enabled
            LOGGER.info("Background changer %s", "enabled" if self.enabled else "disabled")

    def remove_background(self, image):
        """Remove background from an image.

        Args:
            image: PIL.Image object

        Returns:
            PIL.Image with transparent background (RGBA)
        """
        if not self.enabled or not REMBG_AVAILABLE or self.session is None:
            return image

        try:
            # Convert to bytes for rembg
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)

            # Remove background with improved edge detection
            output = remove(
                img_byte_arr.getvalue(),
                session=self.session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=270,
                alpha_matting_background_threshold=20,
                alpha_matting_erode_size=15
            )

            # Convert back to PIL Image
            result = Image.open(io.BytesIO(output))
            return result.convert('RGBA')

        except Exception as e:
            LOGGER.error("Failed to remove background: %s", e)
            return image

    def apply_background(self, foreground, background_path=None, original_size=None):
        """Apply a background to an image with transparent background.

        Args:
            foreground: PIL.Image with transparent background (RGBA)
            background_path: Path to background image (uses current if None)
            original_size: Original image size tuple (width, height) to ensure proper sizing

        Returns:
            PIL.Image with new background (RGB)
        """
        if background_path is None:
            background_path = self.get_current_background()

        if background_path is None:
            LOGGER.warning("No background available")
            return foreground.convert('RGB')

        try:
            # Use original size if provided, otherwise use foreground size
            target_size = original_size if original_size else foreground.size
            LOGGER.debug("Foreground size: %s, Target size: %s", foreground.size, target_size)

            # Load and resize background to match target size
            background = Image.open(background_path)
            background = background.convert('RGB')
            LOGGER.debug("Background original size: %s", background.size)

            background = self._resize_to_cover(background, target_size)
            LOGGER.debug("Background after resize: %s", background.size)

            # Ensure foreground has alpha channel
            if foreground.mode != 'RGBA':
                foreground = foreground.convert('RGBA')

            # Resize foreground to match target size if needed
            if foreground.size != target_size:
                foreground = foreground.resize(target_size, Image.Resampling.LANCZOS)
                LOGGER.debug("Foreground resized to: %s", foreground.size)

            # Composite foreground over background
            background.paste(foreground, (0, 0), foreground)

            return background

        except Exception as e:
            LOGGER.error("Failed to apply background: %s", e)
            return foreground.convert('RGB')

    def _resize_to_cover(self, image, target_size):
        """Resize image to cover target size while maintaining aspect ratio."""
        target_w, target_h = target_size
        img_w, img_h = image.size

        # Calculate scale to cover
        scale = max(target_w / img_w, target_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        # Resize
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        image = image.crop((left, top, left + target_w, top + target_h))

        return image

    def process_image(self, image):
        """Full pipeline: remove background and apply new one.

        Args:
            image: PIL.Image object

        Returns:
            PIL.Image with replaced background
        """
        if not self.enabled or not self.backgrounds:
            return image

        # Check if "No background" is selected (first option)
        current_bg = self.get_current_background()
        if current_bg is None:
            LOGGER.info("'Sans fond' selected - returning original image")
            return image

        LOGGER.info("Processing image with background: %s", self.get_current_background_name())
        LOGGER.info("Original image size: %s", image.size)

        # Save original size before processing
        original_size = image.size

        # Step 1: Remove background
        foreground = self.remove_background(image)

        # Step 2: Apply new background with original size
        result = self.apply_background(foreground, original_size=original_size)

        LOGGER.info("Final image size: %s", result.size)
        return result


@pibooth.hookimpl
def pibooth_configure(cfg):
    """Define plugin configuration options."""
    cfg.add_option(
        SECTION,
        'backgrounds_path',
        "~/.config/pibooth/backgrounds",
        "Path to directory containing background images"
    )
    cfg.add_option(
        SECTION,
        'enabled',
        True,
        "Enable background replacement at startup"
    )
    cfg.add_option(
        SECTION,
        'model',
        "u2net",
        "AI model for background removal (u2net, u2netp, u2net_human_seg, silueta)"
    )
    cfg.add_option(
        SECTION,
        'process_captures',
        True,
        "Process individual captures (True) or only final picture (False)"
    )


@pibooth.hookimpl
def pibooth_startup(cfg, app):
    """Initialize the background changer at startup."""
    global _active_bg_changer

    if not REMBG_AVAILABLE:
        LOGGER.error("rembg package not installed. Install with: pip install rembg[gpu]")
        app.bg_changer = None
        _active_bg_changer = None
        return

    backgrounds_path = cfg.getpath(SECTION, 'backgrounds_path')
    model = cfg.get(SECTION, 'model')

    app.bg_changer = BackgroundChanger(backgrounds_path, model)
    app.bg_changer.enabled = cfg.getboolean(SECTION, 'enabled')

    # Store reference for use in hooks that don't have access to app
    _active_bg_changer = app.bg_changer

    LOGGER.info("Background changer plugin initialized")


@pibooth.hookimpl
def pibooth_cleanup(app):
    """Cleanup resources."""
    if hasattr(app, 'bg_changer') and app.bg_changer:
        app.bg_changer = None
        LOGGER.info("Background changer plugin cleaned up")


def _get_background_thumbnail(bg_path, size=(80, 60)):
    """Get or create a cached thumbnail for the background image."""
    global _thumbnail_cache
    import pygame

    # Handle "No background" case - create a placeholder
    if bg_path is None:
        cache_key = "no_background"
        if cache_key in _thumbnail_cache:
            return _thumbnail_cache[cache_key]

        # Create a simple placeholder with diagonal lines pattern
        placeholder = pygame.Surface(size)
        placeholder.fill((60, 60, 60))  # Dark gray background

        # Draw diagonal lines to indicate "no background"
        line_color = (100, 100, 100)
        for i in range(-size[1], size[0], 10):
            pygame.draw.line(placeholder, line_color, (i, 0), (i + size[1], size[1]), 1)

        # Draw "X" in the center
        pygame.draw.line(placeholder, (150, 150, 150), (10, 10), (size[0]-10, size[1]-10), 2)
        pygame.draw.line(placeholder, (150, 150, 150), (size[0]-10, 10), (10, size[1]-10), 2)

        _thumbnail_cache[cache_key] = placeholder
        return placeholder

    cache_key = str(bg_path)
    if cache_key in _thumbnail_cache:
        return _thumbnail_cache[cache_key]

    try:
        # Load and resize the background image
        bg_image = Image.open(bg_path)
        bg_image.thumbnail(size, Image.Resampling.LANCZOS)

        # Convert PIL Image to pygame surface
        mode = bg_image.mode
        img_size = bg_image.size
        data = bg_image.tobytes()

        if mode == 'RGBA':
            pygame_surface = pygame.image.fromstring(data, img_size, mode)
        else:
            # Convert to RGB if needed
            bg_image = bg_image.convert('RGB')
            data = bg_image.tobytes()
            pygame_surface = pygame.image.fromstring(data, bg_image.size, 'RGB')

        _thumbnail_cache[cache_key] = pygame_surface
        return pygame_surface
    except Exception as e:
        LOGGER.warning("Failed to create thumbnail for %s: %s", bg_path, e)
        return None


def _show_banner():
    """Show the banner and reset the timer."""
    global _banner_last_shown, _banner_visible
    _banner_last_shown = time.time()
    _banner_visible = True


def _should_show_banner():
    """Check if banner should be visible based on timeout."""
    global _banner_visible
    if not _banner_visible:
        return False

    elapsed = time.time() - _banner_last_shown
    if elapsed > BANNER_DISPLAY_TIME:
        _banner_visible = False
        return False
    return True


def _draw_background_info(win, bg_changer):
    """Draw background selection info on the window with thumbnail and touch buttons."""
    import pygame
    global _left_button_rect, _right_button_rect

    if not bg_changer or not bg_changer.backgrounds:
        return

    # Check if banner should be visible
    if not _should_show_banner():
        _left_button_rect = None
        _right_button_rect = None
        return

    # Get window surface
    surface = win.surface

    # Create font (15% larger)
    try:
        font = pygame.font.Font(None, 41)  # 36 * 1.15 ≈ 41
        small_font = pygame.font.Font(None, 32)  # 28 * 1.15 ≈ 32
        button_font = pygame.font.Font(None, 55)  # 48 * 1.15 ≈ 55
    except:
        return

    # Background info
    bg_name = bg_changer.get_current_background_name()
    bg_index = bg_changer.current_index + 1
    bg_total = len(bg_changer.backgrounds)
    bg_path = bg_changer.get_current_background()

    # Position at bottom of screen
    rect = surface.get_rect()
    padding = 17  # 15 * 1.15 ≈ 17
    thumbnail_size = (92, 69)  # (80, 60) * 1.15
    button_size = 58  # 50 * 1.15 ≈ 58

    # Calculate box dimensions (15% larger)
    box_height = 104  # 90 * 1.15 ≈ 104
    box_width = 460  # 400 * 1.15 = 460

    # Calculate box X position (right side of screen)
    box_x = rect.width - box_width

    # Draw semi-transparent background box (bottom-right corner)
    box_surface = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
    box_surface.fill((0, 0, 0, 200))

    # Add a subtle border
    pygame.draw.rect(box_surface, (100, 100, 100, 255), (0, 0, box_width, box_height), 2)

    surface.blit(box_surface, (box_x, rect.height - box_height))

    # Draw left touch button
    left_btn_x = box_x + padding
    left_btn_y = rect.height - box_height + (box_height - button_size) // 2
    _left_button_rect = pygame.Rect(left_btn_x, left_btn_y, button_size, button_size)

    # Left button background
    pygame.draw.rect(surface, (70, 70, 70), _left_button_rect, border_radius=8)
    pygame.draw.rect(surface, (150, 150, 150), _left_button_rect, 2, border_radius=8)

    # Left arrow symbol
    left_arrow = button_font.render("<", True, (255, 255, 255))
    left_arrow_rect = left_arrow.get_rect(center=_left_button_rect.center)
    surface.blit(left_arrow, left_arrow_rect)

    # Draw right touch button
    right_btn_x = box_x + padding + button_size + 12
    right_btn_y = left_btn_y
    _right_button_rect = pygame.Rect(right_btn_x, right_btn_y, button_size, button_size)

    # Right button background
    pygame.draw.rect(surface, (70, 70, 70), _right_button_rect, border_radius=8)
    pygame.draw.rect(surface, (150, 150, 150), _right_button_rect, 2, border_radius=8)

    # Right arrow symbol
    right_arrow = button_font.render(">", True, (255, 255, 255))
    right_arrow_rect = right_arrow.get_rect(center=_right_button_rect.center)
    surface.blit(right_arrow, right_arrow_rect)

    # Text positions (after buttons)
    text_x = box_x + padding + button_size * 2 + 29
    text_start_y = rect.height - box_height + 14

    # Render texts
    title_text = font.render(f"Fond: {bg_name}", True, (255, 255, 255))
    index_text = small_font.render(f"({bg_index}/{bg_total})", True, (200, 200, 200))

    # Draw title
    surface.blit(title_text, (text_x, text_start_y))

    # Draw index below title
    surface.blit(index_text, (text_x, text_start_y + 35))

    # Draw thumbnail on the right side of the banner
    thumbnail = _get_background_thumbnail(bg_path, thumbnail_size)
    if thumbnail:
        thumb_x = box_x + box_width - thumbnail_size[0] - padding
        thumb_y = rect.height - box_height + (box_height - thumbnail_size[1]) // 2

        # Draw a border around the thumbnail
        border_rect = pygame.Rect(thumb_x - 2, thumb_y - 2,
                                  thumbnail_size[0] + 4, thumbnail_size[1] + 4)
        pygame.draw.rect(surface, (255, 255, 255), border_rect, 2)

        surface.blit(thumbnail, (thumb_x, thumb_y))


@pibooth.hookimpl
def state_wait_do(cfg, app, win, events):
    """Handle background selection during wait state.

    Uses left/right arrow keys or touch buttons to change background.
    """
    import pygame
    global _left_button_rect, _right_button_rect

    if not hasattr(app, 'bg_changer') or app.bg_changer is None:
        return

    # Check for left/right key events or touch/mouse clicks to change background
    for event in events:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                app.bg_changer.previous_background()
                _show_banner()  # Show banner when changing background
                LOGGER.info("Background changed to: %s", app.bg_changer.get_current_background_name())
            elif event.key == pygame.K_RIGHT:
                app.bg_changer.next_background()
                _show_banner()  # Show banner when changing background
                LOGGER.info("Background changed to: %s", app.bg_changer.get_current_background_name())

        # Handle touch/mouse clicks on buttons
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos

            # Check if left button was clicked
            if _left_button_rect and _left_button_rect.collidepoint(mouse_pos):
                app.bg_changer.previous_background()
                _show_banner()
                LOGGER.info("Touch: Background changed to: %s", app.bg_changer.get_current_background_name())

            # Check if right button was clicked
            elif _right_button_rect and _right_button_rect.collidepoint(mouse_pos):
                app.bg_changer.next_background()
                _show_banner()
                LOGGER.info("Touch: Background changed to: %s", app.bg_changer.get_current_background_name())

            # If clicked anywhere in banner area, show it again
            else:
                # Check if click is in the banner area (bottom-right, 15% larger)
                rect = win.surface.get_rect()
                box_width = 460  # Updated width
                box_height = 104  # Updated height
                banner_area = pygame.Rect(rect.width - box_width, rect.height - box_height, box_width, box_height)
                if banner_area.collidepoint(mouse_pos):
                    _show_banner()

    # Draw background info overlay (will auto-hide after timeout)
    _draw_background_info(win, app.bg_changer)
    pygame.display.update()


@pibooth.hookimpl(hookwrapper=True, tryfirst=True)
def pibooth_setup_picture_factory(cfg, opt_index, factory):
    """Intercept picture factory setup to process captures before final assembly.

    This hook is called when the picture factory is being set up with captures.
    We modify the captures in the factory before the picture is built.
    """
    # Get the captures from the factory
    if factory and hasattr(factory, '_images') and factory._images:
        # Check if background changer is available (stored in module-level variable)
        if _active_bg_changer is not None and _active_bg_changer.enabled:
            # Check if "No background" is selected
            if _active_bg_changer.get_current_background() is not None:
                LOGGER.info("Processing %d captures with background replacement...",
                           len(factory._images))

                # Convert tuple to list, process, then convert back
                processed_images = []
                for i, capture in enumerate(factory._images):
                    try:
                        LOGGER.info("Processing capture %d/%d...", i + 1, len(factory._images))
                        processed = _active_bg_changer.process_image(capture)
                        processed_images.append(processed)
                        LOGGER.info("Capture %d processed successfully", i + 1)
                    except Exception as e:
                        LOGGER.error("Failed to process capture %d: %s", i + 1, e)
                        processed_images.append(capture)  # Keep original on error

                # Replace factory images with processed ones
                factory._images = tuple(processed_images)
                LOGGER.info("All captures processed, factory images updated")
            else:
                LOGGER.info("'Sans fond' selected - skipping background replacement")

    # Let the original setup happen
    yield


@pibooth.hookimpl
def state_wait_enter(cfg, app, win):
    """Display current background info when entering wait state."""
    if hasattr(app, 'bg_changer') and app.bg_changer:
        status = "ON" if app.bg_changer.enabled else "OFF"
        bg_name = app.bg_changer.get_current_background_name()
        LOGGER.info("Background Changer [%s] - Current: %s (Use LEFT/RIGHT to change)",
                   status, bg_name)
        # Show banner when entering wait state
        _show_banner()
