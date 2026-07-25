from manim import *
from manim_voiceover import VoiceoverScene
from custom_services.system_tts_service import create_system_tts_service
import numpy as np
import os
import re
from pathlib import Path

# MATHPI_ENTERPRISE_SLIM_HEADER_V1

ENTERPRISE_BACKGROUND_ENABLED = True
ENTERPRISE_BACKGROUND_ASSET = "reference_bg_02.png"
ENTERPRISE_BACKGROUND_OPACITY = 0.62
ENTERPRISE_LOGO_ENABLED = True
ENTERPRISE_LOGO_ASSET = "logo_text_trim.png"
TTS_SPEECH_RATE = float(os.environ.get("MATHPI_TTS_SPEECH_RATE", "0.8"))

# render_canvas_profile: {"aspect_ratio": "16:9", "layout_rule": "Use layout_canvas()/layout_zones returned by the project runtime. Do not invent unsupported zone aliases. Fit or clamp durable objects inside safe_box after arrange/scale/next_to/transform.", "manim_frame": {"frame_height": 8.0, "frame_width": 14.222222, "x_range": [-7.111111, 7.111111], "y_range": [-4.0, 4.0]}, "pixel_size": [1920, 1080], "profile_name": "landscape_16_9_server_v1", "reserved_bands": {"caption_band_height": 0.65, "title_band_height": 0.95}, "safe_box": {"x_range": [-6.661111, 6.661111], "y_range": [-3.65, 3.65]}, "version": "2026-06-11"}
config.pixel_width = 1920
config.pixel_height = 1080
config.frame_width = 14.222222
config.frame_height = 8.0

BG = "#F5F5F0"
PRIMARY = "#2E86AB"
SECONDARY = "#A23B72"
ACCENT = "#F18F01"
SUCCESS = "#2A9D8F"
TEXT_1 = "#264653"

class GlobalConfig:
    BG_COLOR = BG
    TEXT_COLOR = TEXT_1
    TITLE_COLOR = TEXT_1
    MAIN_COLOR = PRIMARY
    LINE_COLOR = MAIN_COLOR
    POINT_COLOR = ACCENT
    LABEL_COLOR = TEXT_COLOR
    AUX_LINE_COLOR = SECONDARY
    HIGHLIGHT_COLOR = ACCENT
    FORMULA_COLOR = PRIMARY
    SECONDARY = SECONDARY
    SECONDARY_COLOR = SECONDARY
    GRID_COLOR = SECONDARY_COLOR
    AXIS_COLOR = MAIN_COLOR
    ACCENT_COLOR = ACCENT
    SUCCESS = SUCCESS
    CJK_TEXT_FONT = 'AR PL KaitiM GB'
    FONT_TITLE = 40
    FONT_BODY = 28
    FONT_FORMULA = 32
    FONT_LABEL = 22

    # 兼容 FS_ 前缀的字号命名（支持版式三层面板参数与 LLM 常规写法）
    FS_TITLE = FONT_TITLE
    FS_BODY = FONT_BODY
    FS_FORMULA = FONT_FORMULA
    FS_LABEL = FONT_LABEL
    FS_RESULT = FONT_FORMULA

    # 骨架提示词用到的语义颜色别名
    BASE_COLOR = TEXT_COLOR        # 原图黑色线条
    DRAW_COLOR = AUX_LINE_COLOR    # 辅助线蓝色
    KNOWN_COLOR = SUCCESS          # 持续已知绿色
    FOCUS_COLOR = HIGHLIGHT_COLOR  # 默认焦点：琥珀橙 #F18F01
    FOCUS_COLOR_1 = HIGHLIGHT_COLOR
    FOCUS_COLOR_2 = "#00B4D8"      # 焦点2：宝石蓝 (用于对比或第二组)
    FOCUS_COLOR_3 = "#8338EC"      # 焦点3：皇家紫 (高饱和紫色，非常醒目)
    FOCUS_COLOR_4 = "#FF006E"      # 焦点4：玫瑰红 (极强强调)
    FOCUS_COLOR_5 = "#38B000"      # 焦点5：荧光绿 (清新醒目)

    # 专门用于“对应相等”或“全等”的多组对比色对
    PAIR_A_COLOR = "#E76F51"       # 珊瑚红
    PAIR_B_COLOR = "#2A9D8F"       # 翡翠绿
    PAIR_C_COLOR = "#457B9D"       # 冰川蓝

    TEXT_MUTED_COLOR = "#A0A4A8"   # 已讲过内容淡化灰色
    RESULT_COLOR = ACCENT  # 结论红色
    # 右侧面板物理坐标与版式定义
    RIGHT_X = 1.05
    RIGHT_W = 5.0
    RIGHT_H = 5.85
    RIGHT_CENTER_Y = 0.05
    PROBLEM_SAFE_LEFT = -6.50
    PROBLEM_SAFE_BOTTOM = 1.35
    PROBLEM_LOGO_GAP = 0.22
    PROBLEM_FALLBACK_RIGHT = 4.95
    PROBLEM_BORDER_BUFF = 0.08
    PROBLEM_X = (PROBLEM_SAFE_LEFT + PROBLEM_FALLBACK_RIGHT) / 2
    PROBLEM_Y = 3.16
    PROBLEM_W = PROBLEM_FALLBACK_RIGHT - PROBLEM_SAFE_LEFT - 2 * PROBLEM_BORDER_BUFF
    PROBLEM_MAX_TOP = 3.62
    PROBLEM_MAX_RIGHT = PROBLEM_FALLBACK_RIGHT
    QUESTION_Y = 1.72
    QUESTION_MAX_TOP = 1.94
    QUESTION_MIN_BOTTOM = 1.40
    STEP_MAX_TOP = 1.22
    STEP_MIN_BOTTOM = -3.05
    STEP_CENTER_Y = -0.35

    PROBLEM_FS = 32
    PROBLEM_FS_LONG = 26
    PROBLEM_FS_DENSE = 20
    PROBLEM_FS_EXTRA_DENSE = 16
    PROBLEM_WEIGHT = BOLD
    QUESTION_FS = 22
    Z_PANEL = 10
    Z_REGION = -1

    PROBLEM_COLOR = "#426B85"
    PROBLEM_BORDER_COLOR = "#8DB9D7"

    RANDOM_SEED = 42

# ── 导出语义常量到模块级（让 LLM 直接写 BASE_COLOR 而非 GlobalConfig.BASE_COLOR）──
BASE_COLOR = GlobalConfig.BASE_COLOR
DRAW_COLOR = GlobalConfig.DRAW_COLOR
KNOWN_COLOR = GlobalConfig.KNOWN_COLOR
FOCUS_COLOR = GlobalConfig.FOCUS_COLOR
FOCUS_COLOR_1 = GlobalConfig.FOCUS_COLOR_1
FOCUS_COLOR_2 = GlobalConfig.FOCUS_COLOR_2
FOCUS_COLOR_3 = GlobalConfig.FOCUS_COLOR_3
RESULT_COLOR = GlobalConfig.RESULT_COLOR
PAIR_A_COLOR = GlobalConfig.PAIR_A_COLOR
PAIR_B_COLOR = GlobalConfig.PAIR_B_COLOR
TEXT_COLOR = GlobalConfig.TEXT_COLOR
TEXT_MUTED_COLOR = GlobalConfig.TEXT_MUTED_COLOR

# --- 1a. 企业视觉包运行时覆盖（普通主题无这些变量时无效果）---
if bool(globals().get("ENTERPRISE_BACKGROUND_ENABLED", False)):
    _enterprise_font_name = str(globals().get("ENTERPRISE_CJK_TEXT_FONT", "") or "").strip()
    if _enterprise_font_name:
        GlobalConfig.CJK_TEXT_FONT = _enterprise_font_name
    _enterprise_font_asset = str(globals().get("ENTERPRISE_CJK_FONT_ASSET", "") or "").strip()
    if _enterprise_font_asset and "register_font" in globals():
        try:
            _enterprise_font_rel = Path(_enterprise_font_asset)
            if (
                not _enterprise_font_rel.is_absolute()
                and ".." not in _enterprise_font_rel.parts
                and _enterprise_font_rel.suffix.lower() in {".ttf", ".otf", ".ttc"}
            ):
                _enterprise_assets_dir = Path(os.environ.get("MATHPI_RENDER_ASSETS_DIR", "assets")).resolve()
                _enterprise_font_path = (_enterprise_assets_dir / _enterprise_font_rel).resolve()
                if _enterprise_assets_dir in _enterprise_font_path.parents and _enterprise_font_path.exists():
                    _enterprise_font_context = register_font(str(_enterprise_font_path))
                    _enterprise_font_context.__enter__()
                    globals()["_mathpi_enterprise_cjk_font_context"] = _enterprise_font_context
        except Exception:
            pass

# --- Stable module-level tokens for generated Manim primitives ---
TEXT_COLOR = GlobalConfig.TEXT_COLOR
TITLE_COLOR = GlobalConfig.TITLE_COLOR
FORMULA_COLOR = GlobalConfig.FORMULA_COLOR
LINE_COLOR = GlobalConfig.LINE_COLOR
POINT_COLOR = GlobalConfig.POINT_COLOR
LABEL_COLOR = GlobalConfig.LABEL_COLOR
AUX_LINE_COLOR = GlobalConfig.AUX_LINE_COLOR
HIGHLIGHT_COLOR = GlobalConfig.HIGHLIGHT_COLOR
ACCENT_COLOR = GlobalConfig.ACCENT_COLOR
SECONDARY_COLOR = GlobalConfig.SECONDARY_COLOR
FONT_TITLE = GlobalConfig.FONT_TITLE
FONT_BODY = GlobalConfig.FONT_BODY
FONT_FORMULA = GlobalConfig.FONT_FORMULA
FONT_LABEL = GlobalConfig.FONT_LABEL
FS_TITLE = GlobalConfig.FS_TITLE
FS_BODY = GlobalConfig.FS_BODY
FS_FORMULA = GlobalConfig.FS_FORMULA
FS_LABEL = GlobalConfig.FS_LABEL
FS_RESULT = GlobalConfig.FS_RESULT
_mathpi_cjk_text_font = GlobalConfig.CJK_TEXT_FONT

class BaseConfigScene(VoiceoverScene):
    TITLE_COLOR = GlobalConfig.TITLE_COLOR
    TEXT_COLOR = GlobalConfig.TEXT_COLOR
    FORMULA_COLOR = GlobalConfig.FORMULA_COLOR
    LINE_COLOR = GlobalConfig.LINE_COLOR
    POINT_COLOR = GlobalConfig.POINT_COLOR
    LABEL_COLOR = GlobalConfig.LABEL_COLOR
    AUX_LINE_COLOR = GlobalConfig.AUX_LINE_COLOR
    HIGHLIGHT_COLOR = GlobalConfig.HIGHLIGHT_COLOR
    ACCENT_COLOR = GlobalConfig.ACCENT_COLOR
    SECONDARY_COLOR = GlobalConfig.SECONDARY_COLOR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        template = TexTemplateLibrary.ctex
        template.add_to_preamble(r"\usepackage{amssymb}")
        template.add_to_preamble(r"\usepackage{unicode-math}")
        Tex.set_default(tex_template=template, color=GlobalConfig.TEXT_COLOR)
        MathTex.set_default(tex_template=template, color=GlobalConfig.FORMULA_COLOR)
        Text.set_default(font=GlobalConfig.CJK_TEXT_FONT, color=GlobalConfig.TEXT_COLOR)
        if "MarkupText" in globals() and hasattr(MarkupText, "set_default"):
            MarkupText.set_default(font=GlobalConfig.CJK_TEXT_FONT)
        if "Paragraph" in globals() and hasattr(Paragraph, "set_default"):
            Paragraph.set_default(font=GlobalConfig.CJK_TEXT_FONT)
        Mobject.set_default(color=GlobalConfig.TEXT_COLOR)
        VMobject.set_default(color=GlobalConfig.LINE_COLOR)
        self.camera.background_color = GlobalConfig.BG_COLOR
        np.random.seed(GlobalConfig.RANDOM_SEED)

    def wait(self, duration=DEFAULT_WAIT_TIME, *args, **kwargs):
        if float(duration) <= 0:
            return self
        return super().wait(duration, *args, **kwargs)

    def play(self, *animations, **kwargs):
        if float(kwargs.get("run_time", 1)) <= 0:
            return self
        return super().play(*animations, **kwargs)

    def setup(self):
        super().setup()
        self.setup_layout()

    def setup_layout(self):
        service = create_system_tts_service()
        self.set_speech_service(service)
        self._add_enterprise_background()
        self._add_enterprise_logo()
        self.mount_authoritative_problem_panel()

    def mount_authoritative_problem_panel(self):
        """Mount the externally recognized problem once; generated code never owns it."""
        existing = getattr(self, "_authoritative_problem_panel", None)
        if existing is not None:
            return existing
        text = str(globals().get("AUTHORITATIVE_PROBLEM_TEXT", "") or "").strip()
        if not text:
            return None
        panel = self.make_problem_panel(text.splitlines())
        self.add(panel)
        self._authoritative_problem_panel = panel
        return panel

    def _tts_int_to_cn(self, value):
        value = int(value)
        digits = "零一二三四五六七八九"
        if value < 0:
            return "负" + self._tts_int_to_cn(-value)
        if value < 10:
            return digits[value]
        if value < 20:
            return "十" + (digits[value % 10] if value % 10 else "")
        if value < 100:
            return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
        return "".join(digits[int(ch)] for ch in str(value))

    def normalize_tts_text(self, text):
        content = str(text)

        def decimal_text(match):
            integer = self._tts_int_to_cn(match.group(1))
            decimals = "".join(self._tts_int_to_cn(ch) for ch in match.group(2))
            return f"负{integer}点{decimals}"

        def fraction_text(match):
            numerator = self._tts_int_to_cn(match.group(1))
            denominator = self._tts_int_to_cn(match.group(2))
            return f"负{denominator}分之{numerator}"

        def negative_text(match):
            return "负" + self._tts_int_to_cn(match.group(1))

        content = re.sub(r"负\s*(\d+)\.(\d+)", decimal_text, content)
        content = re.sub(r"(?<![A-Za-z0-9_\u4e00-\u9fff)])-\s*(\d+)\.(\d+)", decimal_text, content)
        content = re.sub(r"负\s*(\d+)\s*/\s*(\d+)", fraction_text, content)
        content = re.sub(r"(?<![A-Za-z0-9_\u4e00-\u9fff)])-\s*(\d+)\s*/\s*(\d+)", fraction_text, content)
        content = re.sub(r"负\s*(\d+)", negative_text, content)
        content = re.sub(r"(?<![A-Za-z0-9_\u4e00-\u9fff)])-\s*(\d+)", negative_text, content)
        for old, new in [
            ("欧埃姆希", "OMC"),
            ("欧埃希", "OAC"),
            ("埃贝希", "ABC"),
            ("贝希", "BC"),
            ("埃希", "AC"),
            ("埃西", "AC"),
            ("欧希", "OC"),
            ("埃姆", "M"),
            ("埃克斯", "x"),
            ("瓦伊", "y"),
        ]:
            content = content.replace(old, new)
        for old, new in [
            ("刻", "k"),
            ("必", "b"),
            ("埃", "A"),
            ("贝", "B"),
            ("希", "C"),
            ("迪", "D"),
            ("欧", "O"),
        ]:
            content = re.sub(rf"(?<![\u4e00-\u9fff]){old}(?![\u4e00-\u9fff])", new, content)
        return content

    def voiceover(self, text=None, **kwargs):
        if text is not None:
            text = self.normalize_tts_text(text)
        return super().voiceover(text=text, **kwargs)

    @staticmethod
    def _enterprise_background_asset_path():
        if not bool(globals().get("ENTERPRISE_BACKGROUND_ENABLED", False)):
            return None
        asset = str(globals().get("ENTERPRISE_BACKGROUND_ASSET", "") or "").strip()
        if not asset:
            return None
        rel_path = Path(asset)
        if rel_path.is_absolute() or ".." in rel_path.parts or rel_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            raise ValueError(f"Unsafe enterprise background asset path: {asset}")
        assets_dir = Path(os.environ.get("MATHPI_RENDER_ASSETS_DIR", "assets")).resolve()
        background_path = (assets_dir / rel_path).resolve()
        if assets_dir not in background_path.parents:
            raise ValueError(f"Enterprise background path escapes assets root: {asset}")
        if not background_path.exists():
            raise RuntimeError(f"MATHPI_ENTERPRISE_BACKGROUND_MISSING: {background_path}")
        return background_path

    @staticmethod
    def _enterprise_background_opacity():
        raw = os.environ.get("MATHPI_BACKGROUND_OPACITY", globals().get("ENTERPRISE_BACKGROUND_OPACITY", 0.62))
        try:
            opacity = float(raw)
        except (TypeError, ValueError):
            opacity = 0.62
        return max(0.0, min(1.0, opacity))

    def _add_enterprise_background(self):
        existing = getattr(self, "_mathpi_enterprise_background_mobject", None)
        if existing is not None and existing in getattr(self, "mobjects", []):
            return existing
        background_path = self._enterprise_background_asset_path()
        if background_path is None:
            return None
        background = ImageMobject(str(background_path))
        background.stretch_to_fit_width(config.frame_width)
        background.stretch_to_fit_height(config.frame_height)
        background.move_to(ORIGIN)
        background.set_opacity(self._enterprise_background_opacity())
        background.set_z_index(-1000)
        self.add(background)
        self._mathpi_enterprise_background_mobject = background
        return background

    @staticmethod
    def _enterprise_logo_asset_path():
        if not bool(globals().get("ENTERPRISE_LOGO_ENABLED", False)):
            return None
        asset = str(globals().get("ENTERPRISE_LOGO_ASSET", "") or "").strip()
        if not asset:
            return None
        rel_path = Path(asset)
        if rel_path.is_absolute() or ".." in rel_path.parts or rel_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError(f"Unsafe enterprise logo asset path: {asset}")
        assets_dir = Path(os.environ.get("MATHPI_RENDER_ASSETS_DIR", "assets")).resolve()
        logo_path = (assets_dir / rel_path).resolve()
        if assets_dir not in logo_path.parents:
            raise ValueError(f"Enterprise logo path escapes assets root: {asset}")
        if not logo_path.exists():
            raise RuntimeError(f"MATHPI_ENTERPRISE_LOGO_MISSING: {logo_path}")
        return logo_path

    def _add_enterprise_logo(self):
        existing = getattr(self, "_mathpi_enterprise_logo_mobject", None)
        if existing is not None and existing in getattr(self, "mobjects", []):
            return existing
        logo_path = self._enterprise_logo_asset_path()
        if logo_path is None:
            return None
        logo = ImageMobject(str(logo_path))
        logo.set_height(float(globals().get("ENTERPRISE_LOGO_HEIGHT", 0.52) or 0.52))
        logo.to_corner(UR, buff=float(globals().get("ENTERPRISE_LOGO_CORNER_BUFF", 0.30) or 0.30))
        logo.set_z_index(1000)
        self._enterprise_logo = logo
        self.add(logo)
        self._mathpi_enterprise_logo_mobject = logo
        return logo

    def play_steps_evenly(self, animations, tracker, active_fraction=0.85, default_run_time=0.7, **kwargs):
        if "spread_fraction" in kwargs:
            active_fraction = kwargs["spread_fraction"]
        if "min_run_time" in kwargs:
            default_run_time = kwargs["min_run_time"]
        raw = [animations] if isinstance(animations, Animation) else list(animations or [])
        items = [
            FadeIn(animation) if isinstance(animation, Mobject) else animation
            for animation in raw
            if animation is not None
        ]
        if not items:
            return
        duration = max(0.0, float(getattr(tracker, "duration", 0.0)))
        window = max(float(default_run_time) * len(items), duration * float(active_fraction))
        run_time = max(0.35, min(1.2, window / max(1, len(items))))
        for animation in items:
            self.play(animation, run_time=run_time)

    def play_after_speech(self, animations, tracker, default_run_time=0.45, max_run_time=0.8):
        raw = [animations] if isinstance(animations, Animation) else list(animations or [])
        items = [animation for animation in raw if animation is not None]
        if not items:
            return
        duration = max(0.0, float(getattr(tracker, "duration", 0.0)))
        if duration > 0:
            self.wait(duration)
        run_time = max(0.25, min(float(max_run_time), float(default_run_time)))
        for animation in items:
            self.play(animation, run_time=run_time)

    # ── 几何布局辅助 ──────────────────────────────────

    def _fit_mobject_to_box(self, mobject, x_range, y_range, buff=0.25):
        """将对象按整体包围盒缩放并居中到指定区域。"""
        target_w = (x_range[1] - x_range[0]) - 2 * buff
        target_h = (y_range[1] - y_range[0]) - 2 * buff
        center_x = (x_range[0] + x_range[1]) / 2
        center_y = (y_range[0] + y_range[1]) / 2
        if target_w <= 0 or target_h <= 0:
            return mobject
        if mobject.width > 0 and mobject.height > 0:
            scale = min(target_w / mobject.width, target_h / mobject.height)
            if scale < 1:
                mobject.scale(scale)
        mobject.move_to(np.array([center_x, center_y, 0]))
        return mobject

    def fit_left(self, mobject, x_range=(-6.25, -0.45), y_range=(-3.05, 1.92), buff=0.25):
        """将几何图形整体缩放+居中到左侧区域。"""
        return self._fit_mobject_to_box(mobject, x_range, y_range, buff)

    def fit_geometry_group(self, *mobjects, x_range=(-6.25, -0.45), y_range=(-3.05, 1.92), buff=0.25):
        """将原图、辅助线、角标、刻痕、标签作为一个整体重新适配左侧图形区。"""
        if len(mobjects) == 1 and isinstance(mobjects[0], (list, tuple)):
            mobjects = tuple(mobjects[0])
        items = [mob for mob in mobjects if mob is not None]
        if not items:
            return Group()
        group = items[0] if len(items) == 1 else Group(*items)
        return self._fit_mobject_to_box(group, x_range, y_range, buff)

    def make_text(self, text, font_size=24, color=None, **kwargs):
        """创建 Text 对象，自动套用项目中文字体和颜色。"""
        text_color = color or getattr(self, "TEXT_COLOR", WHITE)
        max_width = kwargs.pop("max_width", None)
        mob = Text(str(text), font_size=font_size, color=text_color, **kwargs)
        if max_width and mob.width > float(max_width):
            mob.scale_to_fit_width(float(max_width))
        return mob

    def make_formula(self, tex, font_size=None, color=None):
        """Render a pure mathematical expression with MathTex."""
        font_size = font_size or GlobalConfig.FS_FORMULA
        raw = str(tex).replace('\x0c', '\\f').replace('\x08', '\\b').replace('\x09', '\\t')
        mob = MathTex(raw, font_size=font_size, color=color or GlobalConfig.FORMULA_COLOR)
        if mob.width > GlobalConfig.RIGHT_W:
            mob.scale_to_fit_width(GlobalConfig.RIGHT_W)
        return mob

    def make_ctex_row(self, content, font_size=None, color=None, max_width=None):
        """Render one complete Chinese/formula/unit row through Tex + ctex."""
        value = str(content or "").strip()
        if not value:
            return VGroup()
        if "$" not in value and not re.search(r"[\u4e00-\u9fff]", value):
            value = f"${value}$"
        value = re.sub(
            r"(?<!\\)\\\\(?=(?:implies|Rightarrow|frac|dfrac|sqrt|times|cdot|pm|neq|leq|geq|triangle|angle|perp|cong|boldsymbol|quad|Delta|left|right|binom)\b)",
            r"\\",
            value,
        )
        row = Tex(
            value,
            tex_template=TexTemplateLibrary.ctex,
            font_size=font_size or GlobalConfig.FS_BODY,
            color=color or GlobalConfig.TEXT_COLOR,
        )
        limit = GlobalConfig.RIGHT_W if max_width is None else max_width
        if limit is not False and limit and row.width > float(limit):
            row.scale_to_fit_width(float(limit))
        return row

    def make_tex_row(self, content, font_size=None, color=None, max_width=None):
        """Compatibility alias for historical generated code."""
        return self.make_ctex_row(content, font_size=font_size, color=color, max_width=max_width)

    def make_formula_row(self, content, **kwargs):
        """Compatibility alias for one complete ctex row."""
        return self.make_ctex_row(content, font_size=kwargs.get("font_size"), color=kwargs.get("color"), max_width=kwargs.get("max_width"))

    # ── 逐句高亮便捷方法 ──────────────────────────────────

    def _resolve_highlight_color(self, color=None):
        allowed_color_types = (str, int, list, tuple)
        if color is None:
            return GlobalConfig.FOCUS_COLOR
        if isinstance(color, allowed_color_types):
            return color
        return GlobalConfig.FOCUS_COLOR

    def highlight_edge(self, edge_mob, color=None):
        """讲到某条边时：变色"""
        c = self._resolve_highlight_color(color)
        return edge_mob.animate.set_color(c)

    def highlight_angle(self, arc_mob, color=None):
        """讲到某个角时：闪烁膨胀"""
        c = self._resolve_highlight_color(color)
        return Indicate(arc_mob, color=c, scale_factor=1.3)

    def highlight_point(self, mob, color=None):
        """讲到某个点时：Flash 闪光"""
        c = self._resolve_highlight_color(color)
        return Flash(mob, color=c, flash_radius=0.3)

    def highlight_aux(self, aux_mob, color=None):
        """讲到辅助线时：变色 + 扫线"""
        c = self._resolve_highlight_color(color)
        return AnimationGroup(
            aux_mob.animate.set_color(c),
            ShowPassingFlash(
                aux_mob.copy().set_color(c).set_stroke(width=6, opacity=0.8),
                time_width=0.6
            ),
            lag_ratio=0
        )

    def highlight_element(self, mob, color=None):
        """通用元素高亮"""
        c = self._resolve_highlight_color(color)
        return Indicate(mob, color=c, scale_factor=1.08)

    def _stroke_width_of(self, mob, fallback=3):
        """Best-effort stroke width lookup for a VMobject or VGroup."""
        candidates = [mob, *list(getattr(mob, "submobjects", []) or [])]
        for item in candidates:
            try:
                width = item.get_stroke_width()
                if isinstance(width, (list, tuple, np.ndarray)):
                    width = np.array(width, dtype=float).flatten()[0]
                width = float(width)
                if width > 0:
                    return width
            except Exception:
                continue
        return fallback

    def _stroke_color_of(self, mob, fallback=None):
        """Best-effort stroke color lookup for restoring compact marks."""
        candidates = [mob, *list(getattr(mob, "submobjects", []) or [])]
        for item in candidates:
            try:
                color = item.get_stroke_color()
                if color:
                    return color
            except Exception:
                continue
        return fallback

    def _is_compact_mark_group(self, mob):
        """刻痕、平行标记这类小 VGroup 只做细线强调，避免三条线糊成色块。"""
        subs = list(getattr(mob, "submobjects", []) or [])
        if not subs:
            return False
        try:
            max_extent = max(float(getattr(mob, "width", 0) or 0), float(getattr(mob, "height", 0) or 0))
        except Exception:
            max_extent = 0
        if max_extent > 0.65:
            return False
        short_children = 0
        for item in subs:
            try:
                child_extent = max(float(getattr(item, "width", 0) or 0), float(getattr(item, "height", 0) or 0))
                if child_extent <= 0.45:
                    short_children += 1
            except Exception:
                continue
        return short_children >= 1

    def reemphasize_element(self, mob, color=None, scale_factor=1.13):
        """后文再次提到同一线索时：轻微膨胀。适合点、标签、角弧。"""
        c = color or "#2563EB"
        return Indicate(mob, color=c, scale_factor=scale_factor)

    def _reemphasis_overlay(self, mob, color, stroke_width=5, opacity=0.82):
        overlay = mob.copy()
        try:
            overlay.set_color(color)
            overlay.set_stroke(color=color, width=stroke_width, opacity=opacity)
        except Exception:
            pass
        overlay.set_z_index(900)
        return overlay

    def _reemphasize_compact_mark(self, mob, color):
        base_width = self._stroke_width_of(mob, fallback=2)
        base_color = self._stroke_color_of(mob, fallback=None)
        pulse_width = min(max(base_width + 0.8, 2.6), 3.8)
        restore_kwargs = {"width": base_width}
        if base_color is not None:
            restore_kwargs["color"] = base_color
        return AnimationGroup(
            Succession(
                mob.animate.set_stroke(color=color, width=pulse_width, opacity=1),
                Wait(run_time=0.32),
                mob.animate.set_stroke(**restore_kwargs),
            ),
            Indicate(mob, color=color, scale_factor=1.08),
            lag_ratio=0,
        )

    def reemphasize_stroke(self, mob, color=None, stroke_width=5, scale_factor=1.03):
        """后文再次提到线索时：边线扫线；刻痕/平行标记只做细线脉冲。"""
        c = color or "#2563EB"
        if self._is_compact_mark_group(mob):
            return self._reemphasize_compact_mark(mob, c)
        base_width = self._stroke_width_of(mob, fallback=3)
        overlay_width = min(max(base_width + 1.4, 4.0), stroke_width)
        sweep_width = overlay_width + 1.0
        overlay = self._reemphasis_overlay(mob, c, stroke_width=overlay_width, opacity=0.78)
        sweep = self._reemphasis_overlay(mob, c, stroke_width=sweep_width, opacity=0.62)
        return AnimationGroup(
            Succession(
                FadeIn(overlay, run_time=0.12),
                Wait(run_time=0.48),
                FadeOut(overlay, run_time=0.18),
            ),
            ShowPassingFlash(sweep, time_width=0.55),
            Indicate(mob, color=c, scale_factor=scale_factor),
            lag_ratio=0,
        )

    def reemphasize_equal_segments(self, *edge_mobs, color=None):
        """二次强调线段相等：强调真实线段，不强调刻痕或右侧等号。"""
        c = color or "#2563EB"
        animations = []
        for mob in edge_mobs:
            if mob is None:
                continue
            if isinstance(mob, (list, tuple)):
                for item in mob:
                    if item is not None and not self._is_compact_mark_group(item):
                        animations.append(self.reemphasize_stroke(item, color=c))
                continue
            if self._is_compact_mark_group(mob):
                continue
            animations.append(self.reemphasize_stroke(mob, color=c))
        if not animations:
            return Wait(run_time=0.01)
        return AnimationGroup(*animations, lag_ratio=0)

    def _normalize_region_points(self, *points):
        if len(points) == 1 and isinstance(points[0], (list, tuple, VGroup)):
            points = tuple(points[0])
        normalized = []
        for point in points:
            if isinstance(point, Mobject):
                normalized.append(point.get_center())
            else:
                coords = np.asarray(point, dtype=float).reshape(-1)
                if coords.size == 2:
                    coords = np.append(coords, 0.0)
                if coords.size != 3:
                    raise ValueError("区域顶点必须是二维或三维坐标")
                normalized.append(coords)
        return normalized

    def make_region_fill(self, *points, color=None, opacity=0.18, stroke_width=0):
        """几何区域半透明色块。传入缩放后的实际点坐标，如 A, B, C。"""
        pts = self._normalize_region_points(*points)
        region = Polygon(
            *pts,
            fill_color=color or GlobalConfig.FOCUS_COLOR,
            fill_opacity=opacity,
            stroke_width=stroke_width,
        )
        return region.set_z_index(GlobalConfig.Z_REGION)

    def make_area_fill(self, *points, color=None, opacity=0.18, stroke_width=0):
        """历史代码兼容别名；新生成的几何代码使用 make_region_fill。"""
        return self.make_region_fill(*points, color=color, opacity=opacity, stroke_width=stroke_width)

    def make_triangle_region(self, p1, p2, p3, color=None, opacity=0.18):
        """历史代码兼容别名；新生成的几何代码使用 make_region_fill。"""
        return self.make_region_fill(p1, p2, p3, color=color, opacity=opacity)

    def highlight_region(self, region_mob, color=None, opacity=0.28):
        """讲到三角形/四边形区域时：提高填充透明度并轻微强调。"""
        c = color or GlobalConfig.FOCUS_COLOR
        return AnimationGroup(
            region_mob.animate.set_fill(color=c, opacity=opacity),
            Indicate(region_mob, color=c, scale_factor=1.04),
            lag_ratio=0,
        )

    def reemphasize_region(self, region_mob, color=None, opacity=0.26, rest_opacity=0.18, scale_factor=1.05):
        """后文再次提到同一区域时：临时色块层并行出现和淡出，避免串行闪烁。"""
        c = color or "#3F7ECF"
        overlay = region_mob.copy()
        try:
            overlay.set_fill(color=c, opacity=opacity)
            overlay.set_stroke(width=0, opacity=0)
        except Exception:
            pass
        overlay.set_z_index(899)
        return AnimationGroup(
            Succession(
                FadeIn(overlay, run_time=0.12),
                Wait(run_time=0.48),
                FadeOut(overlay, run_time=0.18),
            ),
            Indicate(region_mob, color=c, scale_factor=scale_factor),
            lag_ratio=0,
        )

    def make_right_angle_at(self, vertex, p1, p2, size=0.25, color=None, stroke_width=2):
        """在 vertex 处画直角标记（小方块），p1/p2 是两条射线上的点。"""
        angle_color = color or getattr(self, "LINE_COLOR", WHITE)
        v = np.array(vertex, dtype=float)
        d1 = np.array(p1, dtype=float) - v
        d2 = np.array(p2, dtype=float) - v
        n1 = d1 / max(np.linalg.norm(d1), 1e-9)
        n2 = d2 / max(np.linalg.norm(d2), 1e-9)
        corner1 = v + size * n1
        mid = v + size * n1 + size * n2
        corner2 = v + size * n2
        mark = VGroup(
            Line(corner1, mid, stroke_width=stroke_width, color=angle_color),
            Line(mid, corner2, stroke_width=stroke_width, color=angle_color),
        )
        return mark

    def make_tick_mark(self, edge_mob, n=1, size=0.12, gap=0.08, color=None, stroke_width=2):
        """在一条边（Line mobject）的中点画 n 条垂直短刻痕，表示等边关系。
        n=1 一杠，n=2 二杠，n=3 三杠。"""
        if color is None and not isinstance(size, (int, float, np.number)):
            color, size = size, 0.12
        c = color or getattr(self, "LINE_COLOR", WHITE)
        mid = edge_mob.get_center()
        direction = edge_mob.get_end() - edge_mob.get_start()
        length = np.linalg.norm(direction)
        if length < 1e-9:
            return VGroup()
        tangent = direction / length
        normal = np.array([-tangent[1], tangent[0], 0])

        ticks = VGroup()
        offsets = [(i - (n - 1) / 2) * gap for i in range(n)]
        for off in offsets:
            center = mid + off * tangent
            p1 = center + size * normal
            p2 = center - size * normal
            ticks.add(Line(p1, p2, stroke_width=stroke_width, color=c))
        return ticks

    def make_angle_mark(self, vertex, p1, p2, radius=0.4, color=None, fill_opacity=0.3, stroke_width=2):
        """在 vertex 处，由 p1 和 p2 两条射线夹角确定的正确角度标记（包含扇形色块与圆弧边缘）"""
        v = np.array(vertex, dtype=float)
        d1 = np.array(p1, dtype=float) - v
        d2 = np.array(p2, dtype=float) - v

        theta1 = np.arctan2(d1[1], d1[0])
        theta2 = np.arctan2(d2[1], d2[0])

        angle_diff = (theta2 - theta1 + np.pi) % (2 * np.pi) - np.pi

        if angle_diff < 0:
            start_angle = theta2
            angle = -angle_diff
        else:
            start_angle = theta1
            angle = angle_diff

        mark_color = color or getattr(self, "LINE_COLOR", WHITE)

        sector = Sector(
            radius=radius,
            start_angle=start_angle,
            angle=angle,
            fill_opacity=fill_opacity,
            fill_color=mark_color,
            stroke_width=0,
        )
        sector.shift(v)

        arc = Arc(
            radius=radius,
            start_angle=start_angle,
            angle=angle,
            color=mark_color,
            stroke_width=stroke_width,
        )
        arc.shift(v)

        return VGroup(sector, arc)

    def make_right_angle_mark_at(self, vertex, p1, p2, size=0.25, color=None, fill_opacity=0.3, stroke_width=2):
        """在 vertex 处画直角标记（包含方形色块与两条直角线）"""
        v = np.array(vertex, dtype=float)
        d1 = np.array(p1, dtype=float) - v
        d2 = np.array(p2, dtype=float) - v
        n1 = d1 / max(np.linalg.norm(d1), 1e-9)
        n2 = d2 / max(np.linalg.norm(d2), 1e-9)

        corner1 = v + size * n1
        mid = v + size * n1 + size * n2
        corner2 = v + size * n2

        mark_color = color or getattr(self, "LINE_COLOR", WHITE)

        square = Polygon(
            v, corner1, mid, corner2,
            fill_color=mark_color,
            fill_opacity=fill_opacity,
            stroke_width=0,
        )

        lines = VGroup(
            Line(corner1, mid, stroke_width=stroke_width, color=mark_color),
            Line(mid, corner2, stroke_width=stroke_width, color=mark_color),
        )

        return VGroup(square, lines)

    def place_panel(self, obj, center_y=None):
        """历史代码兼容定位器；make_step_panel 已自动定位。"""
        role = getattr(obj, "_layout_role", "body")
        if role == "problem":
            return self._place_problem_panel(obj)
        if role == "question_goal":
            return self._place_question_goal_panel(obj)
        if obj.width > GlobalConfig.RIGHT_W and obj.width > 0:
            obj.scale_to_fit_width(GlobalConfig.RIGHT_W)
        if obj.height > GlobalConfig.RIGHT_H and obj.height > 0:
            obj.scale_to_fit_height(GlobalConfig.RIGHT_H)
        y = GlobalConfig.RIGHT_CENTER_Y if center_y is None else center_y
        x = GlobalConfig.RIGHT_X + obj.width / 2
        obj.move_to(np.array([x, y, 0]))
        return obj

    def make_panel_lines(self, lines, font_size=None, color=None, line_buff=0.12, max_width=None, weight=None):
        if isinstance(lines, str):
            lines = [line.strip() for line in lines.splitlines() if line.strip()]
        mobs = VGroup()
        for line in lines:
            fs = font_size or GlobalConfig.FS_BODY
            c = color or GlobalConfig.TEXT_COLOR
            limit = max_width or GlobalConfig.RIGHT_W
            # Mobject panel lines must stay as Manim objects; converting them
            # to str() renders object repr text like "Text('...')" on screen.
            if isinstance(line, Mobject):
                mob = line
                if font_size is not None:
                    try:
                        ref = self.make_text("参", font_size=fs, color=c)
                        max_height = ref.height * 1.45
                        if mob.height > max_height and mob.height > 0:
                            mob.scale(max_height / mob.height)
                    except Exception:
                        pass
            else:
                raw_line = str(line)
                # P0-A: 控制字符清理
                raw_line = raw_line.replace('\x0c', '\\f').replace('\x08', '\\b').replace('\x09', '\\t')
                mob = self.make_ctex_row(raw_line, font_size=fs, color=c, max_width=limit)
            mobs.add(mob)
        mobs.arrange(DOWN, aligned_edge=LEFT, buff=line_buff)
        limit = max_width or GlobalConfig.RIGHT_W
        if mobs.width > limit and mobs.width > 0:
            mobs.scale_to_fit_width(limit)
        return mobs

    def _is_panel_latex_line(self, line):
        """Only explicit LaTeX fragments should enter MathTex; panel prose stays Text."""
        raw = str(line)
        if re.search(r"[\u4e00-\u9fff]", raw):
            return False
        if re.search(r"_{2,}", raw):
            return False
        # P0-A: 独立 LaTeX 命令不能单独渲染
        stripped = raw.strip()
        if re.match(r'^\\[A-Za-z]+$', stripped) and stripped in (
            r'\implies', r'\Rightarrow', r'\therefore', r'\because',
            r'\quad', r'\qquad', r'\cdot', r'\pm', r'\mp',
        ):
            return False
        return bool(
            re.search(r"\\(?:frac|dfrac|triangle|sqrt|times|cdot|div|pm|mp|geq|leq|neq|angle|parallel|perp|sim|cong|approx|equiv|infty|sum|prod|int|lim|log|ln|sin|cos|tan|alpha|beta|gamma|delta|theta|pi|phi|lambda|mu|sigma|omega|mathrm|overline|underline|vec|hat|bar|dot|left|right)", raw)
            or re.search(r"(?<!_)_[A-Za-z0-9{]|\\[A-Za-z]+|\\{|\\}|\\^|\^[A-Za-z0-9{]", raw)
        )

    def _escape_problem_panel_text(self, text):
        content = str(text)
        if "$" not in content and re.search(r"\\[A-Za-z]+", content):
            return content
        segments = re.split(r"((?<!\\)\$(?:\\.|[^$])*(?<!\\)\$)", content)
        visible_math = {
            "△": r"$\triangle$", "∠": r"$\angle$",
            "∵": r"$\because$", "∴": r"$\therefore$",
            "⊥": r"$\perp$", "∥": r"$\parallel$",
        }
        for index in range(0, len(segments), 2):
            segment = re.sub(r"(?<!\\)([_%&#])", r"\\\1", segments[index])
            for symbol, tex in visible_math.items():
                segment = segment.replace(symbol, tex)
            segments[index] = segment
        return "".join(segments)

    def make_problem_panel(self, lines):
        import re as _re
        lines = list(lines)
        logo = getattr(self, "_enterprise_logo", None)
        problem_right = GlobalConfig.PROBLEM_FALLBACK_RIGHT
        if logo is not None:
            problem_right = min(problem_right, logo.get_left()[0] - GlobalConfig.PROBLEM_LOGO_GAP)
        line_count = sum(
            1 for line in lines if isinstance(line, Mobject) or str(line).strip()
        )
        if line_count <= 3:
            problem_font_size = GlobalConfig.PROBLEM_FS
        elif line_count <= 4:
            problem_font_size = GlobalConfig.PROBLEM_FS_LONG
        elif line_count <= 5:
            problem_font_size = GlobalConfig.PROBLEM_FS_DENSE
        else:
            problem_font_size = GlobalConfig.PROBLEM_FS_EXTRA_DENSE
        clean_lines = []
        for line in lines:
            if isinstance(line, Mobject):
                clean_lines.append(line)
            else:
                content = _re.sub(r"^\s*\d+\.\s*", "", str(line)).strip()
                content = self._escape_problem_panel_text(content)
                clean_lines.append(self.make_ctex_row(r"\mbox{" + content + "}", font_size=problem_font_size, color=GlobalConfig.PROBLEM_COLOR, max_width=False))
        body = VGroup(*clean_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.07)
        box = SurroundingRectangle(body, color=GlobalConfig.PROBLEM_BORDER_COLOR, stroke_width=1.1, buff=GlobalConfig.PROBLEM_BORDER_BUFF)
        box.set_fill(WHITE, opacity=0.04)
        box.set_z_index(GlobalConfig.Z_PANEL)
        panel = VGroup(box, body)
        panel.set_z_index(GlobalConfig.Z_PANEL)
        panel._layout_role = "problem"
        return self._place_problem_panel(panel)

    def _place_problem_panel(self, panel):
        logo = getattr(self, "_enterprise_logo", None)
        problem_right = GlobalConfig.PROBLEM_FALLBACK_RIGHT
        problem_top = GlobalConfig.PROBLEM_MAX_TOP
        if logo is not None:
            problem_right = min(problem_right, logo.get_left()[0] - GlobalConfig.PROBLEM_LOGO_GAP)
            problem_top = logo.get_top()[1]
        available_w = max(0.1, problem_right - GlobalConfig.PROBLEM_SAFE_LEFT)
        available_h = min(
            1.45,
            max(0.1, problem_top - GlobalConfig.PROBLEM_SAFE_BOTTOM),
        )
        if panel.width > available_w:
            panel.scale_to_fit_width(available_w)
        if panel.height > available_h:
            panel.scale_to_fit_height(available_h)
        if panel.width < available_w * 0.8:
            panel_x = (GlobalConfig.PROBLEM_SAFE_LEFT + problem_right) / 2
        else:
            panel_x = GlobalConfig.PROBLEM_SAFE_LEFT + panel.width / 2
        panel.move_to(np.array([panel_x, problem_top - panel.height / 2, 0]))
        if panel.get_right()[0] > problem_right:
            panel.shift(LEFT * (panel.get_right()[0] - problem_right))
        if panel.get_left()[0] < GlobalConfig.PROBLEM_SAFE_LEFT:
            panel.shift(RIGHT * (GlobalConfig.PROBLEM_SAFE_LEFT - panel.get_left()[0]))
        if panel.get_top()[1] > problem_top:
            panel.shift(DOWN * (panel.get_top()[1] - problem_top))
        if panel.get_bottom()[1] < GlobalConfig.PROBLEM_SAFE_BOTTOM:
            panel.shift(UP * (GlobalConfig.PROBLEM_SAFE_BOTTOM - panel.get_bottom()[1]))
        return panel

    def make_question_goal_panel(self, text):
        panel = VGroup(text) if isinstance(text, Mobject) else VGroup(
            self.make_ctex_row(str(text), font_size=GlobalConfig.QUESTION_FS, color=GlobalConfig.FOCUS_COLOR)
        )
        reference = self.make_text("参", font_size=GlobalConfig.QUESTION_FS, color=GlobalConfig.FOCUS_COLOR)
        if panel.height > 0:
            panel.scale(reference.height / panel.height)
        panel._layout_role = "question_goal"
        return self._place_question_goal_panel(panel)

    def _place_question_goal_panel(self, panel):
        panel.move_to(np.array([GlobalConfig.RIGHT_X + panel.width / 2, GlobalConfig.QUESTION_Y, 0]))
        if panel.get_top()[1] > GlobalConfig.QUESTION_MAX_TOP:
            panel.shift(DOWN * (panel.get_top()[1] - GlobalConfig.QUESTION_MAX_TOP))
        if panel.get_bottom()[1] < GlobalConfig.QUESTION_MIN_BOTTOM:
            panel.shift(UP * (GlobalConfig.QUESTION_MIN_BOTTOM - panel.get_bottom()[1]))
        return panel

    def keep_step_panel_below_goal(self, panel):
        """Keep right-side derivation text below the yellow question goal area."""
        available_h = GlobalConfig.STEP_MAX_TOP - GlobalConfig.STEP_MIN_BOTTOM
        if panel.height > available_h and panel.height > 0:
            panel.scale_to_fit_height(available_h)
            panel.move_to(np.array([GlobalConfig.RIGHT_X + panel.width / 2, (GlobalConfig.STEP_MAX_TOP + GlobalConfig.STEP_MIN_BOTTOM) / 2, 0]))
        if panel.get_top()[1] > GlobalConfig.STEP_MAX_TOP:
            panel.shift(DOWN * (panel.get_top()[1] - GlobalConfig.STEP_MAX_TOP))
        if panel.get_bottom()[1] < GlobalConfig.STEP_MIN_BOTTOM:
            panel.shift(UP * (GlobalConfig.STEP_MIN_BOTTOM - panel.get_bottom()[1]))
        return panel

    def make_step_panel(self, lines, center_y=None):
        import re as _re
        clean_lines = []
        for line in lines:
            if isinstance(line, Mobject):
                clean_lines.append(line)
            else:
                # 过滤常见的行首数字/带圆圈数字序号，如 "1. ", "1、", "(1) ", "① "
                cleaned = _re.sub(r"^\s*(?:\d+[\.、]|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩])\s*", "", str(line))
                clean_lines.append(cleaned)
        panel = self.make_panel_lines(clean_lines, font_size=GlobalConfig.FS_BODY, color=GlobalConfig.TEXT_COLOR, line_buff=0.16)
        self.place_panel(panel, center_y=GlobalConfig.STEP_CENTER_Y if center_y is None else center_y)
        self.keep_step_panel_below_goal(panel)
        return panel


# ── 兼容旧版 Manim 的动画别名容灾 ──────────────────
ShowCreation = Create

class ShowCreationThenFadeOut(Succession):
    def __init__(self, mobject, **kwargs):
        super().__init__(Create(mobject), FadeOut(mobject), **kwargs)

# BatchOps runtime contract: keep visible math symbols stable even when a
# tenant template still contains an older Header implementation.
def _batchops_escape_problem_panel_text(self, text):
    content = str(text)
    if "$" not in content and re.search(r"\\[A-Za-z]+", content):
        return content
    segments = re.split(r"((?<!\\)\$(?:\\.|[^$])*(?<!\\)\$)", content)
    visible_math = {
        "△": r"$\triangle$", "∠": r"$\angle$",
        "∵": r"$\because$", "∴": r"$\therefore$",
        "⊥": r"$\perp$", "∥": r"$\parallel$",
    }
    for index in range(0, len(segments), 2):
        segment = re.sub(r"(?<!\\)([_%&#])", r"\\\1", segments[index])
        for symbol, tex in visible_math.items():
            segment = segment.replace(symbol, tex)
        segments[index] = segment
    return "".join(segments)

BaseConfigScene._escape_problem_panel_text = _batchops_escape_problem_panel_text

def _batchops_clean_proof_formula(formula):
    """Remove guessed prefixes so the Header owns the only visible connector."""
    content = str(formula).strip().lstrip("$").rstrip("$").strip()
    content = re.sub(
        r"^(?:(?:\.{3}|…+|∵|∴|\\because|\\therefore|因为|所以)\s*)+",
        "",
        content,
    )
    return content.strip()

def _batchops_make_proof_because(self, formula):
    """Create a premise row without asking generated code to choose a prefix."""
    content = _batchops_clean_proof_formula(formula)
    return self.make_ctex_row(r"$\because " + content + "$")

def _batchops_make_proof_therefore(self, formula):
    """Create a conclusion row without asking generated code to choose a prefix."""
    content = _batchops_clean_proof_formula(formula)
    return self.make_ctex_row(r"$\therefore " + content + "$")

BaseConfigScene.make_proof_because = _batchops_make_proof_because
BaseConfigScene.make_proof_therefore = _batchops_make_proof_therefore

_batchops_original_make_label_text = getattr(
    BaseConfigScene, "make_label_text", None
)
_batchops_original_make_axes_manual = getattr(
    BaseConfigScene, "make_axes_manual", None
)

def _batchops_make_axes_manual(self, *args, **kwargs):
    axes = _batchops_original_make_axes_manual(self, *args, **kwargs)
    self._batchops_latest_axes = axes
    return axes

def _batchops_bbox_overlap(first, second, margin=0.08):
    return not (
        first.get_right()[0] + margin < second.get_left()[0]
        or first.get_left()[0] - margin > second.get_right()[0]
        or first.get_top()[1] + margin < second.get_bottom()[1]
        or first.get_bottom()[1] - margin > second.get_top()[1]
    )

def _batchops_place_function_label(self, label, anchor, buff=0.12):
    """Choose a stable position beside a graph, away from axes and labels."""
    axes = getattr(self, "_batchops_latest_axes", None)
    if axes is None or not hasattr(anchor, "point_from_proportion"):
        label.next_to(anchor, UR, buff=buff)
        return label
    obstacles = [
        getattr(axes, name, None)
        for name in ("x_axis", "y_axis", "x_label", "y_label")
    ]
    obstacles.extend(getattr(self, "_batchops_function_labels", []))
    obstacles = [item for item in obstacles if item is not None]
    best = None
    for proportion in (0.25, 0.75, 0.4, 0.6):
        point = anchor.point_from_proportion(proportion)
        for direction in (UR, DR, UL, DL):
            candidate = label.copy().next_to(point, direction, buff=buff)
            collisions = sum(
                _batchops_bbox_overlap(candidate, item) for item in obstacles
            )
            frame_penalty = int(
                candidate.get_left()[0] < -6.75
                or candidate.get_right()[0] > 6.75
                or candidate.get_bottom()[1] < -3.75
                or candidate.get_top()[1] > 3.75
            )
            score = collisions * 100 + frame_penalty * 1000
            if best is None or score < best[0]:
                best = (score, candidate)
            if score == 0:
                label.move_to(candidate)
                self._batchops_function_labels = [
                    *getattr(self, "_batchops_function_labels", []), label
                ]
                return label
    if best is not None:
        label.move_to(best[1])
    self._batchops_function_labels = [
        *getattr(self, "_batchops_function_labels", []), label
    ]
    return label

def _batchops_make_label_text(self, text, *args, **kwargs):
    """Normalize and safely place every label anchored to a graph."""
    value = str(text).strip()
    if len(value) >= 2 and value.startswith("$") and value.endswith("$"):
        value = value[1:-1].strip()
    anchor = args[0] if args else kwargs.get("anchor")
    if (
        anchor is not None
        and hasattr(anchor, "point_from_proportion")
    ):
        clean_kwargs = dict(kwargs)
        clean_kwargs.pop("anchor", None)
        direction = clean_kwargs.pop("direction", UR)
        buff = clean_kwargs.pop("buff", 0.12)
        clean_args = args[1:] if args else ()
        label = _batchops_original_make_label_text(
            self, value, None, *clean_args, direction=direction, buff=buff,
            **clean_kwargs
        )
        return _batchops_place_function_label(self, label, anchor, buff=buff)
    return _batchops_original_make_label_text(self, value, *args, **kwargs)

def _batchops_make_function_label(self, text, graph, **kwargs):
    """Public ABI for collision-aware function-expression labels."""
    return _batchops_make_label_text(self, text, graph, **kwargs)

if _batchops_original_make_axes_manual is not None:
    BaseConfigScene.make_axes_manual = _batchops_make_axes_manual
if _batchops_original_make_label_text is not None:
    BaseConfigScene.make_label_text = _batchops_make_label_text
    BaseConfigScene.make_function_label = _batchops_make_function_label

# BatchOps typography/lifecycle contract. Keep this patch after tenant Headers
# so old database templates cannot silently restore body shrinking or pre-reveal.
BATCHOPS_BODY_FONT_SIZE = 36
GlobalConfig.FONT_BODY = BATCHOPS_BODY_FONT_SIZE
GlobalConfig.FS_BODY = BATCHOPS_BODY_FONT_SIZE
GlobalConfig.FONT_FORMULA = BATCHOPS_BODY_FONT_SIZE
GlobalConfig.FS_FORMULA = BATCHOPS_BODY_FONT_SIZE
GlobalConfig.FS_RESULT = BATCHOPS_BODY_FONT_SIZE

_batchops_original_make_ctex_row = BaseConfigScene.make_ctex_row
_batchops_original_make_panel_lines = BaseConfigScene.make_panel_lines

def _batchops_make_ctex_row_uniform(
    self, content, font_size=None, color=None, max_width=None
):
    """Make every board row use the one authoritative body size."""
    requested_size = GlobalConfig.FS_BODY
    effective_width = float("inf") if max_width is None else max_width
    row = _batchops_original_make_ctex_row(
        self,
        content,
        font_size=requested_size,
        color=color,
        max_width=effective_width,
    )
    row._mathpi_typography_role = "body_row"
    row._mathpi_nominal_font_size = GlobalConfig.FS_BODY
    return row

def _batchops_make_panel_lines_uniform(
    self,
    lines,
    font_size=None,
    color=None,
    line_buff=0.12,
    max_width=None,
    weight=None,
):
    """Arrange FS_BODY rows without shrinking rows or their whole group."""
    source_lines = (
        [line.strip() for line in lines.splitlines() if line.strip()]
        if isinstance(lines, str)
        else list(lines or [])
    )
    rows = VGroup()
    for line in source_lines:
        row = (
            line
            if isinstance(line, Mobject)
            else self.make_ctex_row(
                str(line),
                font_size=GlobalConfig.FS_BODY,
                color=color or GlobalConfig.TEXT_COLOR,
                max_width=None,
            )
        )
        row._mathpi_typography_role = "body_row"
        row._mathpi_nominal_font_size = GlobalConfig.FS_BODY
        rows.add(row)
    rows.arrange(DOWN, aligned_edge=LEFT, buff=line_buff)
    rows._mathpi_typography_role = "body_rows"
    return rows

BaseConfigScene.make_ctex_row = _batchops_make_ctex_row_uniform
BaseConfigScene.make_panel_lines = _batchops_make_panel_lines_uniform

def _batchops_make_problem_panel_readable(self, lines):
    """Render mixed problem text directly; never nest math inside one mbox."""
    clean_lines = []
    problem_font_size = GlobalConfig.FS_BODY
    for line in list(lines or []):
        if isinstance(line, Mobject):
            row = line
        else:
            content = re.sub(r"^\s*\d+\.\s*", "", str(line)).strip()
            if not content:
                continue
            row = self.make_ctex_row(
                self._escape_problem_panel_text(content),
                font_size=problem_font_size,
                color=GlobalConfig.PROBLEM_COLOR,
                max_width=float("inf"),
            )
        row._mathpi_typography_role = "problem_row"
        row._mathpi_nominal_font_size = problem_font_size
        clean_lines.append(row)
    body = VGroup(*clean_lines).arrange(
        DOWN, aligned_edge=LEFT, buff=0.07
    )
    box = SurroundingRectangle(
        body,
        color=GlobalConfig.PROBLEM_BORDER_COLOR,
        stroke_width=1.1,
        buff=GlobalConfig.PROBLEM_BORDER_BUFF,
    )
    box.set_fill(WHITE, opacity=0.04)
    box.set_z_index(GlobalConfig.Z_PANEL)
    panel = VGroup(box, body)
    panel.set_z_index(GlobalConfig.Z_PANEL)
    panel._layout_role = "problem"
    return self._place_problem_panel(panel)

BaseConfigScene.make_problem_panel = _batchops_make_problem_panel_readable

if hasattr(BaseConfigScene, "make_formula_stack"):
    def _batchops_make_formula_stack_uniform(
        self, steps=None, line_buff=0.22, max_width=None, max_height=None
    ):
        """Register a stable stack without progressively shrinking its rows."""
        rows = VGroup(*list(steps or []))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=line_buff)
        rows.move_to(
            np.array([GlobalConfig.CALC_MAIN_X, GlobalConfig.CALC_REGION_Y, 0])
        )
        rows._calculation_row_scale = 1.0
        rows._mathpi_typography_role = "body_rows"
        self.add(rows)
        return rows

    def _batchops_push_formula_step_uniform(
        self, stack, step, mute_history=True, muted_color=None, line_buff=0.22
    ):
        """Hide a future row before attaching it; caller reveals it exactly once."""
        if mute_history:
            history_color = muted_color or GlobalConfig.TEXT_MUTED_COLOR
            for row in stack:
                row.set_color(history_color)
        step.set_opacity(0)
        step._mathpi_typography_role = "body_row"
        step._mathpi_nominal_font_size = GlobalConfig.FS_BODY
        stack.add(step)
        stack.arrange(DOWN, aligned_edge=LEFT, buff=line_buff)
        stack.move_to(
            np.array([GlobalConfig.CALC_MAIN_X, GlobalConfig.CALC_REGION_Y, 0])
        )
        stack._calculation_row_scale = 1.0
        return step

    BaseConfigScene.make_formula_stack = _batchops_make_formula_stack_uniform
    BaseConfigScene.push_formula_step = _batchops_push_formula_step_uniform


class Solution(BaseConfigScene):
    def get_intersection(self, p1, p2, p3, p4):
        x1, y1 = p1[0], p1[1]
        x2, y2 = p2[0], p2[1]
        x3, y3 = p3[0], p3[1]
        x4, y4 = p4[0], p4[1]
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-6:
            return (p1 + p2) / 2
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
        return np.array([px, py, 0])

    def construct(self):
        # ================= 图 1 原始坐标与定义 =================
        A1 = np.array([-4.75, -1.5, 0])
        B1 = np.array([-1.25, -1.5, 0])
        C1 = np.array([-3.0, 1.53, 0])

        edge_A1B1 = Line(A1, B1, color=BASE_COLOR)
        edge_B1C1 = Line(B1, C1, color=BASE_COLOR)
        edge_C1A1 = Line(C1, A1, color=BASE_COLOR)
        diagram1 = VGroup(edge_A1B1, edge_B1C1, edge_C1A1)

        # 适配左侧
        self.fit_left(diagram1)

        # 获取图 1 实时坐标
        pt_A1 = edge_A1B1.get_start()
        pt_B1 = edge_A1B1.get_end()
        pt_C1 = edge_B1C1.get_end()
        pt_D1 = edge_C1A1.point_from_proportion(0.4)
        pt_P1 = edge_B1C1.point_from_proportion(0.4)
        pt_Q1 = self.get_intersection(pt_A1, pt_P1, pt_B1, pt_D1)

        # 创建图 1 其他元素
        line_AP1 = Line(pt_A1, pt_P1, color=BASE_COLOR)
        line_BD1 = Line(pt_B1, pt_D1, color=BASE_COLOR)
        dot_A1 = Dot(pt_A1, radius=0.04, color=BASE_COLOR)
        dot_B1 = Dot(pt_B1, radius=0.04, color=BASE_COLOR)
        dot_C1 = Dot(pt_C1, radius=0.04, color=BASE_COLOR)
        dot_D1 = Dot(pt_D1, radius=0.04, color=BASE_COLOR)
        dot_P1 = Dot(pt_P1, radius=0.04, color=BASE_COLOR)
        dot_Q1 = Dot(pt_Q1, radius=0.04, color=BASE_COLOR)

        lbl_A1 = MathTex("A", color=TEXT_COLOR).next_to(dot_A1, DOWN + LEFT, buff=0.15)
        lbl_B1 = MathTex("B", color=TEXT_COLOR).next_to(dot_B1, DOWN + RIGHT, buff=0.15)
        lbl_C1 = MathTex("C", color=TEXT_COLOR).next_to(dot_C1, UP, buff=0.15)
        lbl_D1 = MathTex("D", color=TEXT_COLOR).next_to(dot_D1, LEFT, buff=0.15)
        lbl_P1 = MathTex("P", color=TEXT_COLOR).next_to(dot_P1, RIGHT, buff=0.15)
        lbl_Q1 = MathTex("Q", color=TEXT_COLOR).next_to(dot_Q1, DOWN, buff=0.15)
        lbl_fig1 = Text("图1", font_size=20, color=TEXT_COLOR).move_to(pt_A1 + DOWN * 0.8 + RIGHT * 1.5)

        tick_CD1 = self.make_tick_mark(Line(pt_C1, pt_D1), n=1, color=KNOWN_COLOR)
        tick_BP1 = self.make_tick_mark(Line(pt_B1, pt_P1), n=1, color=KNOWN_COLOR)

        arc_ABP1 = self.make_angle_mark(pt_B1, pt_A1, pt_P1, radius=0.3, color=FOCUS_COLOR, fill_opacity=0.25)
        arc_C1 = self.make_angle_mark(pt_C1, pt_A1, pt_B1, radius=0.3, color=FOCUS_COLOR, fill_opacity=0.25)

        region_ABP1 = self.make_region_fill(pt_A1, pt_B1, pt_P1, color=PAIR_A_COLOR, opacity=0.18)
        region_BCD1 = self.make_region_fill(pt_B1, pt_C1, pt_D1, color=PAIR_B_COLOR, opacity=0.18)

        geometry_all1 = VGroup(
            diagram1, line_AP1, line_BD1, dot_A1, dot_B1, dot_C1, dot_D1, dot_P1, dot_Q1,
            lbl_A1, lbl_B1, lbl_C1, lbl_D1, lbl_P1, lbl_Q1, lbl_fig1,
            tick_CD1, tick_BP1, arc_ABP1, arc_C1, region_ABP1, region_BCD1
        )
        self.fit_geometry_group(geometry_all1)

        # ================= 图 2 原始坐标与定义 =================
        A2 = np.array([1.8, -1.5, 0])
        B2 = np.array([4.2, -1.5, 0])
        C2 = np.array([3.0, 0.58, 0])
        D2 = np.array([1.32, -2.332, 0])
        P2 = np.array([2.52, 1.412, 0])

        edge_A2B2 = Line(A2, B2, color=BASE_COLOR)
        edge_B2C2 = Line(B2, C2, color=BASE_COLOR)
        edge_C2A2 = Line(C2, A2, color=BASE_COLOR)
        ext_AD = Line(A2, D2, color=BASE_COLOR)
        ext_CP = Line(C2, P2, color=BASE_COLOR)
        diagram2 = VGroup(edge_A2B2, edge_B2C2, edge_C2A2, ext_AD, ext_CP)

        self.fit_left(diagram2)

        # 获取图 2 实时坐标
        pt_A2 = edge_A2B2.get_start()
        pt_B2 = edge_A2B2.get_end()
        pt_C2 = edge_B2C2.get_end()
        pt_D2 = ext_AD.get_end()
        pt_P2 = ext_CP.get_end()
        pt_Q2 = self.get_intersection(pt_A2, pt_P2, pt_B2, pt_D2)

        # 创建图 2 其他元素
        line_AP2 = Line(pt_A2, pt_P2, color=BASE_COLOR)
        line_BD2 = Line(pt_B2, pt_D2, color=BASE_COLOR)
        dot_A2 = Dot(pt_A2, radius=0.04, color=BASE_COLOR)
        dot_B2 = Dot(pt_B2, radius=0.04, color=BASE_COLOR)
        dot_C2 = Dot(pt_C2, radius=0.04, color=BASE_COLOR)
        dot_D2 = Dot(pt_D2, radius=0.04, color=BASE_COLOR)
        dot_P2 = Dot(pt_P2, radius=0.04, color=BASE_COLOR)
        dot_Q2 = Dot(pt_Q2, radius=0.04, color=BASE_COLOR)

        lbl_A2 = MathTex("A", color=TEXT_COLOR).next_to(dot_A2, UP + LEFT, buff=0.15)
        lbl_B2 = MathTex("B", color=TEXT_COLOR).next_to(dot_B2, DOWN + RIGHT, buff=0.15)
        lbl_C2 = MathTex("C", color=TEXT_COLOR).next_to(dot_C2, RIGHT, buff=0.15)
        lbl_D2 = MathTex("D", color=TEXT_COLOR).next_to(dot_D2, LEFT, buff=0.15)
        lbl_P2 = MathTex("P", color=TEXT_COLOR).next_to(dot_P2, UP, buff=0.15)
        lbl_Q2 = MathTex("Q", color=TEXT_COLOR).next_to(dot_Q2, DOWN, buff=0.15)
        lbl_fig2 = Text("图2", font_size=20, color=TEXT_COLOR).move_to(pt_A2 + DOWN * 0.8 + RIGHT * 1.5)

        tick_CD2 = self.make_tick_mark(Line(pt_C2, pt_D2), n=1, color=KNOWN_COLOR)
        tick_BP2 = self.make_tick_mark(Line(pt_B2, pt_P2), n=1, color=KNOWN_COLOR)

        arc_BQP2 = self.make_angle_mark(pt_Q2, pt_B2, pt_P2, radius=0.3, color=RESULT_COLOR, fill_opacity=0.25)
        arc_ABP2 = self.make_angle_mark(pt_B2, pt_A2, pt_P2, radius=0.3, color=FOCUS_COLOR, fill_opacity=0.25)
        arc_BCD2 = self.make_angle_mark(pt_C2, pt_B2, pt_D2, radius=0.3, color=FOCUS_COLOR, fill_opacity=0.25)

        region_ABP2 = self.make_region_fill(pt_A2, pt_B2, pt_P2, color=PAIR_A_COLOR, opacity=0.18)
        region_BCD2 = self.make_region_fill(pt_B2, pt_C2, pt_D2, color=PAIR_B_COLOR, opacity=0.18)

        geometry_all2 = VGroup(
            diagram2, line_AP2, line_BD2, dot_A2, dot_B2, dot_C2, dot_D2, dot_P2, dot_Q2,
            lbl_A2, lbl_B2, lbl_C2, lbl_D2, lbl_P2, lbl_Q2, lbl_fig2,
            tick_CD2, tick_BP2, arc_BQP2, arc_ABP2, arc_BCD2, region_ABP2, region_BCD2
        )
        self.fit_geometry_group(geometry_all2)

        # ================= 动画播放：第一问 =================
        base_geometry1 = VGroup(
            diagram1, line_AP1, line_BD1, dot_A1, dot_B1, dot_C1, dot_D1, dot_P1, dot_Q1,
            lbl_A1, lbl_B1, lbl_C1, lbl_D1, lbl_P1, lbl_Q1, lbl_fig1
        )
        self.add(base_geometry1)

        with self.voiceover(text="同学们好！我们一起来看这道题。") as tracker:
            pass

        with self.voiceover(text="首先，题目给出三角形 ABC 是等边三角形。") as tracker:
            self.play_after_speech([
                self.highlight_edge(edge_A1B1),
                self.highlight_edge(edge_B1C1),
                self.highlight_edge(edge_C1A1)
            ], tracker)

        with self.voiceover(text="动点 D 在边 CA 上，动点 P 在边 BC 上。") as tracker:
            self.play_after_speech([
                self.highlight_point(lbl_D1),
                self.highlight_point(lbl_P1)
            ], tracker)

        with self.voiceover(text="它们分别从 C 点和 B 点同时出发。") as tracker:
            pass

        with self.voiceover(text="并且以相同的速度进行运动。") as tracker:
            pass

        with self.voiceover(text="因为速度相同，所以它们运动的距离相等，也就是线段 CD 等于 BP。") as tracker:
            self.play_after_speech([
                FadeIn(tick_CD1),
                FadeIn(tick_BP1)
            ], tracker)

        with self.voiceover(text="连接 AP 和 BD，它们相交于点 Q。") as tracker:
            self.play_after_speech([
                self.highlight_edge(line_AP1),
                self.highlight_edge(line_BD1),
                self.highlight_point(lbl_Q1)
            ], tracker)

        with self.voiceover(text="第一问要求证：线段 AP 等于 BD。") as tracker:
            goal_panel = self.make_question_goal_panel(self.make_ctex_row(r"求证：$AP = BD$"))
            self.play_after_speech([FadeIn(goal_panel)], tracker)

        with self.voiceover(text="要证 AP 等于 BD，我们可以尝试寻找全等三角形。") as tracker:
            self.play_steps_evenly([
                self.reemphasize_stroke(line_AP1),
                self.reemphasize_stroke(line_BD1)
            ], tracker)

        with self.voiceover(text="我们注意到，AP 在三角形 ABP 中。") as tracker:
            self.play_steps_evenly([FadeIn(region_ABP1)], tracker)

        with self.voiceover(text="而 BD 在三角形 BCD 中。") as tracker:
            self.play_steps_evenly([FadeIn(region_BCD1)], tracker)

        with self.voiceover(text="我们来看看这两个三角形有哪些相等的条件。") as tracker:
            pass

        with self.voiceover(text="首先，因为三角形 ABC 是等边三角形，所以 AB 等于 BC。") as tracker:
            self.play_steps_evenly([
                self.reemphasize_equal_segments(edge_A1B1, edge_B1C1)
            ], tracker)

        with self.voiceover(text="同时，等边三角形的每个内角都是六十度。") as tracker:
            pass

        with self.voiceover(text="所以角 ABP 等于角 C，都等于六十度。") as tracker:
            self.play_steps_evenly([
                FadeIn(arc_ABP1),
                FadeIn(arc_C1)
            ], tracker)

        with self.voiceover(text="再加上已知条件中，BP 等于 CD。") as tracker:
            self.play_steps_evenly([
                self.reemphasize_equal_segments(Line(pt_B1, pt_P1), Line(pt_C1, pt_D1))
            ], tracker)

        with self.voiceover(text="这样，我们就可以用边角边定理，证明这两个三角形全等。") as tracker:
            pass

        step_panel1 = self.make_step_panel([
            self.make_proof_because(r"\triangle ABC \text{ 是等边三角形}"),
            self.make_proof_therefore(r"AB = BC, \angle ABP = \angle C = 60^\circ"),
            self.make_proof_because(r"BP = CD"),
            self.make_proof_therefore(r"\triangle ABP \cong \triangle BCD\ (SAS)"),
            self.make_proof_therefore(r"AP = BD")
        ])

        with self.voiceover(text="因为三角形 ABC 是等边三角形，所以 AB 等于 BC，且角 ABP 等于角 C 等于六十度。") as tracker:
            self.play_steps_evenly([
                Write(step_panel1[0]),
                Write(step_panel1[1])
            ], tracker)

        with self.voiceover(text="又因为已知条件中，BP 等于 CD。") as tracker:
            self.play_steps_evenly([Write(step_panel1[2])], tracker)

        with self.voiceover(text="所以，三角形 ABP 全等于三角形 BCD。") as tracker:
            self.play_steps_evenly([Write(step_panel1[3])], tracker)

        with self.voiceover(text="全等三角形的对应边相等，因此 AP 等于 BD。第一问得证。") as tracker:
            self.play_steps_evenly([Write(step_panel1[4])], tracker)

        # ================= 动画播放：第二问 =================
        with self.voiceover(text="接下来我们看第二问。") as tracker:
            self.play(
                FadeOut(geometry_all1),
                FadeOut(goal_panel),
                FadeOut(step_panel1)
            )

        base_geometry2 = VGroup(
            diagram2, line_AP2, line_BD2, dot_A2, dot_B2, dot_C2, dot_D2, dot_P2, dot_Q2,
            lbl_A2, lbl_B2, lbl_C2, lbl_D2, lbl_P2, lbl_Q2, lbl_fig2
        )

        with self.voiceover(text="如果把动点 D 和 P 的范围，改为在射线 CA 和射线 BC 上运动。") as tracker:
            self.play(FadeIn(base_geometry2))

        with self.voiceover(text="此时，我们需要证明：角 BQP 的大小保持不变，且等于六十度。") as tracker:
            goal_panel2 = self.make_question_goal_panel(self.make_ctex_row(r"求证：$\angle BQP = 60^\circ$"))
            self.play_after_speech([FadeIn(goal_panel2)], tracker)

        with self.voiceover(text="我们同样来寻找全等三角形。") as tracker:
            pass

        with self.voiceover(text="注意到此时 D 在 CA 延长线上，P 在 BC 延长线上。") as tracker:
            self.play_steps_evenly([
                self.reemphasize_stroke(ext_AD),
                self.reemphasize_stroke(ext_CP)
            ], tracker)

        with self.voiceover(text="因为它们依然以相同的速度运动，所以 BP 仍然等于 CD。") as tracker:
            self.play_steps_evenly([
                FadeIn(tick_CD2),
                FadeIn(tick_BP2)
            ], tracker)

        with self.voiceover(text="我们再次关注三角形 ABP 和三角形 BCD。") as tracker:
            self.play_steps_evenly([
                FadeIn(region_ABP2),
                FadeIn(region_BCD2)
            ], tracker)

        with self.voiceover(text="此时，AB 依然等于 BC。") as tracker:
            self.play_steps_evenly([
                self.reemphasize_equal_segments(edge_A2B2, edge_B2C2)
            ], tracker)

        with self.voiceover(text="那它们的夹角呢？") as tracker:
            pass

        with self.voiceover(text="角 ABP 是等边三角形外角，等于一百二十度。") as tracker:
            self.play_steps_evenly([FadeIn(arc_ABP2)], tracker)

        with self.voiceover(text="角 BCD 也是外角，同样等于一百二十度。") as tracker:
            self.play_steps_evenly([FadeIn(arc_BCD2)], tracker)

        with self.voiceover(text="因此，角 ABP 等于角 BCD。") as tracker:
            pass

        step_panel2 = self.make_step_panel([
            self.make_proof_because(r"\triangle ABC \text{ 是等边三角形}"),
            self.make_proof_therefore(r"AB = BC, \angle ABP = \angle BCD = 120^\circ"),
            self.make_proof_because(r"BP = CD"),
            self.make_proof_therefore(r"\triangle ABP \cong \triangle BCD\ (SAS)")
        ])

        with self.voiceover(text="因为三角形 ABC 是等边三角形，所以 AB 等于 BC，且夹角 ABP 等于 BCD 等于一百二十度。") as tracker:
            self.play_steps_evenly([
                Write(step_panel2[0]),
                Write(step_panel2[1])
            ], tracker)

        with self.voiceover(text="结合 BP 等于 CD，我们依然可以证明三角形 ABP 全等于三角形 BCD。") as tracker:
            self.play_steps_evenly([
                Write(step_panel2[2]),
                Write(step_panel2[3])
            ], tracker)

        step_panel3 = self.make_step_panel([
            self.make_proof_therefore(r"\angle BAP = \angle CBD"),
            self.make_proof_because(r"\angle BQP = \angle BAP + \angle ABQ"),
            self.make_proof_therefore(r"\angle BQP = \angle CBD + \angle ABQ = \angle ABC = 60^\circ")
        ])

        with self.voiceover(text="由全等三角形性质，我们得到对应角相等，即角 BAP 等于角 CBD。") as tracker:
            self.play(FadeOut(step_panel2))
            self.play_steps_evenly([Write(step_panel3[0])], tracker)

        with self.voiceover(text="接下来，我们来看目标角 BQP。") as tracker:
            self.play_steps_evenly([FadeIn(arc_BQP2)], tracker)

        with self.voiceover(text="利用三角形外角性质，角 BQP 等于角 BAP 加上角 ABQ。") as tracker:
            self.play_steps_evenly([Write(step_panel3[1])], tracker)

        with self.voiceover(text="将角 BAP 替换为角 CBD，那么角 BQP 就等于角 CBD 加上角 ABQ。") as tracker:
            pass

        with self.voiceover(text="而角 CBD 加上角 ABQ，正好等于等边三角形的内角 ABC，也就是六十度。") as tracker:
            self.play_steps_evenly([Write(step_panel3[2])], tracker)

        # ================= 收尾与总结 =================
        with self.voiceover(text="所以，无论动点如何运动，角 BQP 的大小都保持六十度不变。第二问得证。") as tracker:
            self.play_steps_evenly([self.reemphasize_element(arc_BQP2)], tracker)

        with self.voiceover(text="这道题的关键在于，通过等边三角形的对称性构造全等。") as tracker:
            pass

        with self.voiceover(text="进而实现边与角的等量转移。") as tracker:
            pass

        with self.voiceover(text="掌握了这种转化思想，类似的几何动点问题就能迎刃而解了。") as tracker:
            pass

        with self.voiceover(text="同学们，我们下期再见！") as tracker:
            self.play(
                FadeOut(step_panel3),
                FadeOut(goal_panel2)
            )

if __name__ == "__main__":
    from pathlib import Path as _Path
    from manim import config as _config
    _config.pixel_width = 854
    _config.pixel_height = 480
    _config.frame_rate = 15
    _config.media_dir = "/work/output"
    _config.output_file = "video"
    Solution().render()
