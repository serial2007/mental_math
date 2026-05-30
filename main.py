#!/usr/bin/env python3
"""Kivy Android frontend for the mental math trainer."""

from __future__ import annotations

import json
import os
import random
import time
from io import BytesIO
from pathlib import Path
from typing import Callable

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import escape_markup

import mental_math as engine


OPERATION_ORDER = ["add", "sub", "mul", "div", "square", "sqrt", "det2", "det3"]
DIFFICULTY_ORDER = ["easy", "medium", "hard"]
DIFFICULTY_FROM_LABEL = {label: key for key, label in engine.DIFFICULTY_LABELS.items()}


def android_status_bar_height() -> float:
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        resources = activity.getResources()
        resource_id = resources.getIdentifier("status_bar_height", "dimen", "android")
        return float(resources.getDimensionPixelSize(resource_id)) if resource_id else 0.0
    except Exception:
        return 0.0


def force_adjust_resize() -> None:
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        layout_params = autoclass("android.view.WindowManager$LayoutParams")
        activity.getWindow().setSoftInputMode(layout_params.SOFT_INPUT_ADJUST_RESIZE)
    except Exception:
        pass


def default_config() -> dict[str, object]:
    return {
        "count": 20,
        "difficulty": "medium",
        "precision": 2,
        "operations": [],
    }


def default_stats() -> dict[str, object]:
    return {
        "sessions": 0,
        "shown": 0,
        "answered": 0,
        "correct": 0,
        "skipped": 0,
        "total_score": 0,
        "best_score": 0,
        "best_streak": 0,
        "last_session": None,
    }


def read_json(path: Path, fallback: dict[str, object]) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    return data if isinstance(data, dict) else fallback


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wrong_answer_markup(raw_answer: str, correct_answer: str) -> str:
    user = raw_answer.strip()
    wrong, missing = engine.diff_answer_text(user, correct_answer)
    pieces: list[str] = []
    for char, is_wrong in zip(user, wrong):
        escaped = escape_markup(char)
        pieces.append(f"[color=#b91c1c][b]{escaped}[/b][/color]" if is_wrong else escaped)
    highlighted = "".join(pieces) or "[color=#b91c1c][b](blank)[/b][/color]"
    lines = [f"Wrong: {highlighted}", f"Correct: [b]{escape_markup(correct_answer)}[/b]"]
    if missing:
        lines.insert(1, f"Missing: [color=#a16207][b]{escape_markup(', '.join(missing))}[/b][/color]")
    return "\n".join(lines)


def configure_latex_fonts() -> None:
    from matplotlib import rcParams

    rcParams["mathtext.fontset"] = "cm"
    rcParams["font.family"] = "serif"
    rcParams["font.serif"] = [
        "Computer Modern Roman",
        "CMU Serif",
        "Latin Modern Roman",
        "DejaVu Serif",
    ]


def latex_to_texture(expression: str, font_size: float, dpi: int):
    try:
        app = App.get_running_app()
        cache_base = Path(app.user_data_dir) if app is not None else Path.cwd()
        cache_dir = cache_base / "matplotlib_cache"
        cache_dir.mkdir(exist_ok=True)
        os.environ.setdefault("MPLBACKEND", "Agg")
        os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

        from matplotlib import figure
        from matplotlib.font_manager import FontProperties
        from matplotlib.mathtext import MathTextParser

        configure_latex_fonts()
        buffer = BytesIO()
        math_expression = f"${expression}$"
        prop = FontProperties(family="serif", size=font_size)
        parser = MathTextParser("path")
        width, height, depth, *_ = parser.parse(math_expression, dpi=72, prop=prop)
        fig = figure.Figure(
            figsize=(width / 72.0, height / 72.0),
            facecolor=(1, 1, 1, 0),
        )
        fig.patch.set_alpha(0)
        fig.text(0, depth / height, math_expression, fontproperties=prop, color="#111827")
        fig.savefig(
            buffer,
            dpi=dpi,
            format="png",
            transparent=True,
            facecolor=(1, 1, 1, 0),
            edgecolor=(1, 1, 1, 0),
        )
        buffer.seek(0)
        texture = CoreImage(buffer, ext="png").texture
        texture.mag_filter = "linear"
        texture.min_filter = "linear"
        return texture
    except Exception as exc:
        print(f"Formula bitmap render failed: {exc}")
        return None


def determinant_to_texture(matrix: tuple[tuple[str, ...], ...], font_size: float, dpi: int):
    try:
        os.environ.setdefault("MPLBACKEND", "Agg")

        from matplotlib import get_data_path
        from matplotlib.font_manager import FontProperties, findfont
        from PIL import Image, ImageDraw, ImageFont

        configure_latex_fonts()
        font_px = max(42, int(font_size * dpi / 72))
        try:
            cmr10 = findfont(FontProperties(family="cmr10"), fallback_to_default=False)
        except Exception:
            cmr10 = str(Path(get_data_path()) / "fonts" / "ttf" / "cmr10.ttf")
        try:
            font = ImageFont.truetype(cmr10, font_px)
        except Exception:
            font = ImageFont.load_default()

        probe = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        draw = ImageDraw.Draw(probe)

        def text_width(text: str) -> int:
            if not text:
                return 0
            return int(draw.textlength(text, font=font))

        def text_height(text: str = "-1000") -> int:
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            return bottom - top

        def split_number(text: str) -> tuple[str, str, str]:
            if "." not in text:
                return text, "", ""
            left, right = text.split(".", 1)
            return left, ".", right

        rows = [[split_number(value) for value in row] for row in matrix]
        column_count = len(rows[0])
        left_widths = [0] * column_count
        right_widths = [0] * column_count
        dot_width = text_width(".")
        has_decimal = [False] * column_count
        for row in rows:
            for column, (left, dot, right) in enumerate(row):
                left_widths[column] = max(left_widths[column], text_width(left))
                right_widths[column] = max(right_widths[column], text_width(right))
                has_decimal[column] = has_decimal[column] or bool(dot)

        cell_heights = [text_height(value) for row in matrix for value in row]
        cell_height = max(cell_heights) if cell_heights else text_height()
        row_gap = int(font_px * 0.42)
        column_gap = int(font_px * 0.82)
        bar_gap = int(font_px * 0.24)
        bar_width = max(4, int(font_px * 0.045))
        padding_x = int(font_px * 0.18)
        padding_y = int(font_px * 0.20)
        equals_gap = int(font_px * 0.36)
        equals_width = text_width("=")

        column_widths = [
            left_widths[column] + (dot_width if has_decimal[column] else 0) + right_widths[column]
            for column in range(column_count)
        ]
        matrix_width = sum(column_widths) + column_gap * (column_count - 1)
        matrix_height = len(rows) * cell_height + row_gap * (len(rows) - 1)
        image_width = (
            padding_x * 2
            + bar_width * 2
            + bar_gap * 2
            + matrix_width
            + equals_gap
            + equals_width
        )
        image_height = padding_y * 2 + matrix_height

        image = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        color = (17, 24, 39, 255)
        matrix_x = padding_x + bar_width + bar_gap
        matrix_y = padding_y
        left_bar_x = padding_x
        right_bar_x = matrix_x + matrix_width + bar_gap
        draw.rounded_rectangle((left_bar_x, padding_y, left_bar_x + bar_width, padding_y + matrix_height), radius=bar_width // 2, fill=color)
        draw.rounded_rectangle((right_bar_x, padding_y, right_bar_x + bar_width, padding_y + matrix_height), radius=bar_width // 2, fill=color)

        column_x = matrix_x
        for column in range(column_count):
            decimal_x = column_x + left_widths[column]
            for row_index, row in enumerate(rows):
                left, dot, right = row[column]
                y = matrix_y + row_index * (cell_height + row_gap)
                draw.text((decimal_x - text_width(left), y), left, font=font, fill=color)
                if dot:
                    draw.text((decimal_x, y), dot, font=font, fill=color)
                    draw.text((decimal_x + dot_width, y), right, font=font, fill=color)
            column_x += column_widths[column] + column_gap

        equals_x = right_bar_x + bar_width + equals_gap
        equals_y = padding_y + (matrix_height - cell_height) / 2
        draw.text((equals_x, equals_y), "=", font=font, fill=color)

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        texture = CoreImage(buffer, ext="png").texture
        texture.mag_filter = "linear"
        texture.min_filter = "linear"
        return texture
    except Exception as exc:
        print(f"Determinant bitmap render failed: {exc}")
        return None


class Pill(Label):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.markup = True
        self.font_size = sp(13)
        self.bold = True
        self.color = (0.12, 0.16, 0.22, 1)
        self.size_hint_y = None
        self.height = dp(30)


class OperationButton(Button):
    selected = BooleanProperty(False)

    def __init__(self, operation: str, on_toggle: Callable[[str, bool], None], **kwargs) -> None:
        super().__init__(**kwargs)
        self.operation = operation
        self.on_toggle = on_toggle
        self.text = engine.OPERATION_SYMBOLS[operation]
        self.font_size = sp(18)
        self.bold = True
        self.background_normal = ""
        self.background_down = ""
        self.background_disabled_normal = ""
        self.size_hint = (None, None)
        self.size = (dp(38), dp(40))
        self.bind(on_release=self.toggle)
        self.bind(selected=self.update_style)
        self.update_style()

    def toggle(self, *_args) -> None:
        self.selected = not self.selected
        self.on_toggle(self.operation, self.selected)

    def update_style(self, *_args) -> None:
        if self.selected:
            self.background_color = (0.12, 0.47, 0.78, 1)
            self.color = (1, 1, 1, 1)
        else:
            self.background_color = (0.88, 0.91, 0.94, 1)
            self.color = (0.08, 0.12, 0.18, 1)


class FormulaView(AnchorLayout):
    def __init__(self, **kwargs) -> None:
        super().__init__(anchor_x="center", anchor_y="center", **kwargs)
        self.color = (0.05, 0.09, 0.16, 1)
        self.current_problem: engine.Problem | None = None
        self.message = ""
        self.bind(size=lambda *_args: Clock.schedule_once(self.refresh, 0))
        self.set_message("Select operations, then Start")

    def set_message(self, text: str) -> None:
        self.current_problem = None
        self.message = text
        self.height = self.message_height()
        self.clear_widgets()
        label = Label(
            text=text,
            color=self.color,
            font_size=sp(28),
            bold=True,
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda instance, *_args: setattr(instance, "text_size", instance.size))
        self.add_widget(label)

    def set_problem(self, problem: engine.Problem) -> None:
        self.current_problem = problem
        self.height = self.problem_height(problem)
        self.clear_widgets()
        self.add_widget(self.render_problem(problem))

    def refresh(self, *_args) -> None:
        if self.current_problem is not None:
            self.set_problem(self.current_problem)
        elif self.message:
            self.set_message(self.message)

    def font_for(self, visible_chars: int, max_size: float = 58.0, min_size: float = 24.0) -> float:
        available = max(dp(240), (self.width or Window.width) - dp(36))
        fitted = available / max(1.0, visible_chars * 0.58)
        return max(sp(min_size), min(sp(max_size), fitted))

    def formula_label(self, text: str, font_size: float, bold: bool = True, width: float | None = None) -> Label:
        label = Label(
            text=text,
            color=self.color,
            font_size=font_size,
            bold=bold,
            halign="center",
            valign="middle",
            size_hint=(None, None),
        )
        label.texture_update()
        label.width = width if width is not None else label.texture_size[0] + dp(8)
        label.height = label.texture_size[1] + dp(8)
        label.text_size = label.size
        return label

    def formula_row(self, spacing: float | None = None) -> BoxLayout:
        row = BoxLayout(orientation="horizontal", spacing=spacing if spacing is not None else dp(10), size_hint=(None, None))
        row.bind(minimum_width=row.setter("width"), minimum_height=row.setter("height"))
        return row

    def render_problem(self, problem: engine.Problem) -> Widget:
        if problem.matrix is not None:
            texture = determinant_to_texture(problem.matrix, self.determinant_font_size(problem.matrix), self.latex_dpi())
            if texture is not None:
                return self.texture_image(texture)

        latex = problem.latex.strip()
        texture = latex_to_texture(latex, self.latex_font_size(latex), self.latex_dpi())
        if texture is not None:
            return self.texture_image(texture)
        return self.formula_label(problem.prompt.strip(), self.font_for(len(problem.prompt)))

    def determinant_font_size(self, matrix: tuple[tuple[str, ...], ...]) -> float:
        return 34.0 if len(matrix) <= 2 else 30.0

    def message_height(self) -> float:
        return dp(82)

    def problem_height(self, problem: engine.Problem) -> float:
        if problem.matrix is None:
            return dp(88)
        return dp(108) if len(problem.matrix) <= 2 else dp(116)

    def latex_font_size(self, latex: str) -> float:
        visible = (
            latex.replace(r"\times", "x")
            .replace(r"\frac", "")
            .replace(r"\sqrt", "")
            .replace(r"\left", "")
            .replace(r"\right", "")
            .replace(r"\substack", "")
            .replace(r"\quad", " ")
            .replace("\\", "")
            .replace("{", "")
            .replace("}", "")
        )
        return max(24.0, min(42.0, 560.0 / max(10, len(visible))))

    def latex_dpi(self) -> int:
        window_dpi = getattr(Window, "dpi", 0) or 320
        return max(260, min(420, int(window_dpi)))

    def texture_image(self, texture) -> KivyImage:
        texture_width, texture_height = texture.size
        max_width = max(dp(240), (self.width or Window.width) - dp(36))
        max_height = max(dp(64), (self.height or self.message_height()) - dp(6))
        scale = min(max_width / texture_width, max_height / texture_height)
        image = KivyImage(
            texture=texture,
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(None, None),
            size=(texture_width * scale, texture_height * scale),
        )
        return image


class MentalMathAndroidApp(App):
    title = "Mental Math"

    def build(self):
        Window.clearcolor = (0.95, 0.96, 0.98, 1)
        Window.softinput_mode = "resize"

        self.config_path = Path(self.user_data_dir) / "mental_math_config.json"
        self.stats_path = Path(self.user_data_dir) / "mental_math_stats.json"
        self.user_config = self.load_user_config()
        self.stats = read_json(self.stats_path, default_stats())

        self.operations: list[str] = []
        self.per_operation: dict[str, list[int]] = {}
        self.current_problem: engine.Problem | None = None
        self.current_index = 0
        self.correct = 0
        self.skipped = 0
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.started_at = 0.0
        self.question_started_at = 0.0
        self.session_active = False
        self.session_recorded = False
        self.awaiting_retry = False
        self.empty_submit_allowed_at = 0.0

        top_padding = max(dp(12), android_status_bar_height() + dp(8))
        root = BoxLayout(orientation="vertical", padding=(dp(12), top_padding, dp(12), dp(12)), spacing=dp(6))

        controls = GridLayout(cols=4, spacing=dp(8), size_hint_y=None, height=dp(44))
        self.count_input = self.small_input(str(self.user_config["count"]), "Count")
        self.precision_input = self.small_input(str(self.user_config["precision"]), "Decimals")
        self.difficulty_spinner = Spinner(
            text=engine.DIFFICULTY_LABELS[str(self.user_config["difficulty"])],
            values=[engine.DIFFICULTY_LABELS[key] for key in DIFFICULTY_ORDER],
            size_hint_y=None,
            height=dp(40),
        )
        self.style_button(self.difficulty_spinner, (0.91, 0.94, 0.96, 1), (0.08, 0.12, 0.18, 1))
        self.start_button = Button(text="Start", size_hint_y=None, height=dp(40), bold=True)
        self.style_button(self.start_button, (0.12, 0.47, 0.78, 1), (1, 1, 1, 1))
        self.start_button.bind(on_release=lambda *_args: self.start_quiz())
        controls.add_widget(self.count_input)
        controls.add_widget(self.difficulty_spinner)
        controls.add_widget(self.precision_input)
        controls.add_widget(self.start_button)
        root.add_widget(controls)

        op_row = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(40))
        selected = set(self.user_config["operations"]) if isinstance(self.user_config["operations"], list) else set()
        self.operation_buttons: dict[str, OperationButton] = {}
        for operation in OPERATION_ORDER:
            button = OperationButton(operation, self.on_operation_toggled)
            button.selected = operation in selected
            self.operation_buttons[operation] = button
            op_row.add_widget(button)
        root.add_widget(op_row)

        status_row = GridLayout(cols=4, spacing=dp(6), size_hint_y=None, height=dp(32))
        self.score_label = Pill()
        self.streak_label = Pill()
        self.best_label = Pill()
        self.level_label = Pill()
        for widget in (self.score_label, self.streak_label, self.best_label, self.level_label):
            status_row.add_widget(widget)
        root.add_widget(status_row)

        self.progress = ProgressBar(max=max(1, int(self.user_config["count"])), value=0, size_hint_y=None, height=dp(8))
        root.add_widget(self.progress)

        self.progress_label = Label(
            text="Ready",
            color=(0.24, 0.29, 0.36, 1),
            font_size=sp(15),
            size_hint_y=None,
            height=dp(24),
        )
        root.add_widget(self.progress_label)

        self.formula_view = FormulaView(size_hint_y=None, height=dp(82))
        root.add_widget(self.formula_view)

        self.feedback_label = Label(
            text="",
            markup=True,
            color=(0.20, 0.25, 0.32, 1),
            font_size=sp(13),
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(58),
        )
        self.feedback_label.bind(size=lambda instance, *_args: setattr(instance, "text_size", instance.size))
        root.add_widget(self.feedback_label)

        action_row = GridLayout(cols=4, spacing=dp(8), size_hint_y=None, height=dp(44))
        self.cursor_left_button = Button(text="<", disabled=True)
        self.style_button(self.cursor_left_button, (0.88, 0.91, 0.94, 1), (0.08, 0.12, 0.18, 1))
        self.cursor_left_button.bind(on_release=lambda *_args: self.move_cursor(-1))
        self.cursor_right_button = Button(text=">", disabled=True)
        self.style_button(self.cursor_right_button, (0.88, 0.91, 0.94, 1), (0.08, 0.12, 0.18, 1))
        self.cursor_right_button.bind(on_release=lambda *_args: self.move_cursor(1))
        self.clear_button = Button(text="Clear", disabled=True)
        self.style_button(self.clear_button, (0.88, 0.91, 0.94, 1), (0.08, 0.12, 0.18, 1))
        self.clear_button.bind(on_release=lambda *_args: self.clear_answer())
        self.submit_button = Button(text="Submit", disabled=True)
        self.style_button(self.submit_button, (0.12, 0.47, 0.78, 1), (1, 1, 1, 1))
        self.submit_button.bind(on_release=lambda *_args: self.submit_answer())
        for widget in (
            self.cursor_left_button,
            self.cursor_right_button,
            self.clear_button,
            self.submit_button,
        ):
            action_row.add_widget(widget)
        root.add_widget(action_row)

        answer_row = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(50))
        self.answer_input = TextInput(
            multiline=False,
            hint_text="answer",
            font_size=sp(24),
            input_type="number",
            input_filter=self.answer_filter,
            keyboard_suggestions=False,
            unfocus_on_touch=False,
            disabled=True,
        )
        self.style_text_input(self.answer_input)
        self.answer_input.bind(on_text_validate=lambda *_args: self.submit_answer())
        self.answer_input.bind(on_touch_down=self.on_answer_touch)
        answer_row.add_widget(self.answer_input)
        root.add_widget(answer_row)
        root.add_widget(Widget(size_hint_y=None, height=dp(44)))

        root.add_widget(Widget(size_hint_y=1))

        self.update_game_status()
        self.update_summary()
        return root

    def small_input(self, value: str, hint: str) -> TextInput:
        input_widget = TextInput(
            text=value,
            hint_text=hint,
            multiline=False,
            font_size=sp(18),
            input_filter="int",
            input_type="number",
            keyboard_suggestions=False,
            size_hint_y=None,
            height=dp(40),
        )
        self.style_text_input(input_widget)
        return input_widget

    def style_button(self, button: Button, background: tuple[float, float, float, float], color: tuple[float, float, float, float]) -> None:
        button.background_normal = ""
        button.background_down = ""
        button.background_disabled_normal = ""
        button.background_color = background
        button.color = color
        button.disabled_color = color

    def style_text_input(self, input_widget: TextInput) -> None:
        input_widget.background_normal = ""
        input_widget.background_active = ""
        input_widget.background_disabled_normal = ""
        input_widget.background_color = (1, 1, 1, 1)
        input_widget.foreground_color = (0.08, 0.12, 0.18, 1)
        input_widget.disabled_foreground_color = (0.08, 0.12, 0.18, 1)
        input_widget.hint_text_color = (0.45, 0.49, 0.56, 1)

    def answer_filter(self, substring: str, _from_undo: bool) -> str:
        return "".join(char for char in substring if char in "0123456789.-")

    def load_user_config(self) -> dict[str, object]:
        config = default_config()
        saved = read_json(self.config_path, config)
        count = saved.get("count")
        if isinstance(count, int) and count > 0:
            config["count"] = count
        precision = saved.get("precision")
        if isinstance(precision, int) and 0 <= precision <= 12:
            config["precision"] = precision
        difficulty = saved.get("difficulty")
        if difficulty in engine.DIFFICULTY_LABELS:
            config["difficulty"] = difficulty
        operations = saved.get("operations")
        if isinstance(operations, list):
            config["operations"] = [op for op in operations if op in engine.GENERATORS]
        return config

    def selected_operations(self) -> list[str]:
        return [operation for operation, button in self.operation_buttons.items() if button.selected]

    def on_operation_toggled(self, _operation: str, _selected: bool) -> None:
        self.save_config()
        selected = self.selected_operations()
        if not self.session_active:
            return
        if not selected:
            self.feedback_label.text = "[color=#b91c1c][b]Select at least one operation.[/b][/color]"
            return
        self.operations = selected
        for operation in selected:
            self.per_operation.setdefault(engine.OPERATION_LABELS[operation], [0, 0])

    def selected_difficulty(self) -> str:
        return DIFFICULTY_FROM_LABEL[self.difficulty_spinner.text]

    def selected_count(self) -> int:
        try:
            return max(1, min(999, int(self.count_input.text)))
        except ValueError:
            return 20

    def selected_precision(self) -> int:
        try:
            return max(0, min(12, int(self.precision_input.text)))
        except ValueError:
            return 2

    def save_config(self) -> None:
        write_json(
            self.config_path,
            {
                "count": self.selected_count(),
                "difficulty": self.selected_difficulty(),
                "precision": self.selected_precision(),
                "operations": self.selected_operations(),
            },
        )

    def set_active(self, active: bool) -> None:
        self.answer_input.disabled = not active
        self.cursor_left_button.disabled = not active
        self.cursor_right_button.disabled = not active
        self.clear_button.disabled = not active
        self.submit_button.disabled = not active
        self.count_input.disabled = active
        self.precision_input.disabled = active
        self.difficulty_spinner.disabled = active
        if not active:
            self.answer_input.hide_keyboard()
            self.answer_input.focus = False

    def start_quiz(self) -> None:
        self.record_session()
        operations = self.selected_operations()
        if not operations:
            self.feedback_label.text = "[color=#b91c1c][b]Select at least one operation.[/b][/color]"
            self.save_config()
            return

        self.save_config()
        self.operations = operations
        self.per_operation = engine.make_stats(operations)
        self.current_index = 0
        self.correct = 0
        self.skipped = 0
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.started_at = time.monotonic()
        self.session_active = True
        self.session_recorded = False
        self.progress.max = self.selected_count()
        self.progress.value = 0
        self.feedback_label.text = ""
        self.start_button.text = "Restart"
        self.set_active(True)
        self.next_problem()

    def next_problem(self) -> None:
        total = self.selected_count()
        if self.current_index >= total:
            self.finish_quiz()
            return

        self.current_index += 1
        selected = self.selected_operations()
        if selected:
            self.operations = selected
            for selected_operation in selected:
                self.per_operation.setdefault(engine.OPERATION_LABELS[selected_operation], [0, 0])
        operation = random.choice(self.operations)
        self.current_problem = engine.GENERATORS[operation](self.selected_difficulty(), self.selected_precision())
        self.question_started_at = time.monotonic()
        self.formula_view.set_problem(self.current_problem)
        self.feedback_label.text = ""
        self.progress.value = self.current_index - 1
        self.answer_input.text = ""
        self.awaiting_retry = False
        self.empty_submit_allowed_at = 0.0
        self.focus_answer()
        Clock.schedule_once(self.focus_answer, 0)
        Clock.schedule_once(self.focus_answer, 0.15)
        self.update_summary()

    def focus_answer(self, *_args) -> None:
        if self.session_active and self.current_problem is not None and not self.answer_input.disabled:
            self.answer_input.focus = True
            self.answer_input.show_keyboard()

    def on_answer_touch(self, instance: TextInput, touch) -> None:
        if not instance.collide_point(*touch.pos) or instance.disabled or not self.session_active:
            return
        if instance.focus and not getattr(Window, "keyboard_height", 0):
            instance.focus = False
        Clock.schedule_once(self.focus_answer, 0)

    def move_cursor(self, delta: int) -> None:
        if self.answer_input.disabled:
            return
        index = self.answer_input.cursor_index()
        next_index = max(0, min(len(self.answer_input.text), index + delta))
        self.answer_input.cursor = self.answer_input.get_cursor_from_index(next_index)
        self.answer_input.focus = True

    def clear_answer(self) -> None:
        if self.answer_input.disabled:
            return
        self.answer_input.text = ""
        self.answer_input.cursor = (0, 0)
        self.answer_input.focus = True

    def submit_answer(self) -> None:
        if self.current_problem is None:
            return
        raw = self.answer_input.text.strip()
        if not raw:
            if self.awaiting_retry and time.monotonic() < self.empty_submit_allowed_at:
                self.focus_answer()
                return
            self.skip_problem()
            return

        elapsed = time.monotonic() - self.question_started_at
        op_stats = self.per_operation[self.current_problem.operation]
        if not self.awaiting_retry:
            op_stats[1] += 1
        if engine.check_answer(self.current_problem, raw, self.selected_precision()):
            points = engine.points_for_correct_answer(self.selected_difficulty(), elapsed, self.streak)
            self.score += points
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.correct += 1
            if not self.awaiting_retry:
                op_stats[0] += 1
            self.feedback_label.text = f"[color=#047857][b]Correct +{points}[/b][/color]"
            self.awaiting_retry = False
            self.empty_submit_allowed_at = 0.0
            self.update_game_status()
            self.next_problem()
        else:
            self.streak = 0
            self.awaiting_retry = True
            self.feedback_label.text = wrong_answer_markup(raw, self.current_problem.display_answer)
            self.answer_input.text = ""
            self.answer_input.cursor = (0, 0)
            self.empty_submit_allowed_at = time.monotonic() + 0.35
            self.update_game_status()
            self.update_summary()
            self.focus_answer()

    def skip_problem(self) -> None:
        if self.current_problem is None:
            return
        self.skipped += 1
        self.streak = 0
        self.awaiting_retry = False
        self.empty_submit_allowed_at = 0.0
        self.feedback_label.text = f"Skipped. Answer: [b]{escape_markup(self.current_problem.display_answer)}[/b]"
        self.update_game_status()
        self.next_problem()

    def finish_quiz(self) -> None:
        self.progress.value = self.selected_count()
        self.formula_view.set_message("Finished")
        self.progress_label.text = "Session complete"
        self.current_problem = None
        self.set_active(False)
        self.start_button.text = "Start"
        self.record_session()
        self.update_summary()

    def update_game_status(self) -> None:
        self.score_label.text = f"Score\n{self.score}"
        self.streak_label.text = f"Streak\n{self.streak}"
        self.best_label.text = f"Best\n{self.best_streak}"
        self.level_label.text = f"Level\n{engine.level_for_score(self.score)}"

    def update_summary(self) -> None:
        answered = sum(op_answered for _, op_answered in self.per_operation.values())
        total = self.selected_count()
        if self.session_active:
            accuracy = engine.accuracy_percent(self.correct, answered)
            self.progress_label.text = (
                f"{self.current_index}/{total}  "
                f"Correct {self.correct}/{answered}  "
                f"{accuracy:.1f}%"
            )

    def record_session(self) -> None:
        if not self.session_active or self.session_recorded:
            return
        answered = sum(op_answered for _, op_answered in self.per_operation.values())
        elapsed = time.monotonic() - self.started_at if self.started_at else 0.0
        self.stats["sessions"] = int(self.stats.get("sessions", 0)) + 1
        self.stats["shown"] = int(self.stats.get("shown", 0)) + self.current_index
        self.stats["answered"] = int(self.stats.get("answered", 0)) + answered
        self.stats["correct"] = int(self.stats.get("correct", 0)) + self.correct
        self.stats["skipped"] = int(self.stats.get("skipped", 0)) + self.skipped
        self.stats["total_score"] = int(self.stats.get("total_score", 0)) + self.score
        self.stats["best_score"] = max(int(self.stats.get("best_score", 0)), self.score)
        self.stats["best_streak"] = max(int(self.stats.get("best_streak", 0)), self.best_streak)
        self.stats["last_session"] = {
            "shown": self.current_index,
            "answered": answered,
            "correct": self.correct,
            "skipped": self.skipped,
            "score": self.score,
            "best_streak": self.best_streak,
            "elapsed_seconds": round(elapsed, 3),
            "difficulty": self.selected_difficulty(),
            "precision": self.selected_precision(),
            "operations": self.selected_operations(),
        }
        write_json(self.stats_path, self.stats)
        self.session_recorded = True
        self.session_active = False

    def on_stop(self) -> None:
        self.record_session()
        self.save_config()


if __name__ == "__main__":
    MentalMathAndroidApp().run()
