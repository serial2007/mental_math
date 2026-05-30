#!/usr/bin/env python3
"""Mental arithmetic trainer with a Qt GUI by default."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, localcontext
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Callable


Operation = str
Difficulty = str
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "mental_math_config.json"
STATS_PATH = APP_DIR / "mental_math_stats.json"

OPERATION_LABELS: dict[Operation, str] = {
    "add": "Addition",
    "sub": "Subtraction",
    "mul": "Multiplication",
    "div": "Division",
    "square": "Square",
    "sqrt": "Square root",
    "det2": "2x2 determinant",
    "det3": "3x3 determinant",
}

OPERATION_SYMBOLS: dict[Operation, str] = {
    "add": "+",
    "sub": "-",
    "mul": "×",
    "div": "÷",
    "square": "x²",
    "sqrt": "√",
    "det2": "|2|",
    "det3": "|3|",
}

DIFFICULTY_LABELS: dict[Difficulty, str] = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
}

DIFFICULTY_SCORE: dict[Difficulty, int] = {
    "easy": 100,
    "medium": 180,
    "hard": 280,
}

SPEED_TARGET_SECONDS: dict[Difficulty, float] = {
    "easy": 12.0,
    "medium": 22.0,
    "hard": 40.0,
}


@dataclass(frozen=True)
class Problem:
    prompt: str
    latex: str
    answer: Decimal
    display_answer: str
    operation: str
    approximate: bool = False
    matrix: tuple[tuple[str, ...], ...] | None = None


def random_int(difficulty: Difficulty, ranges: dict[Difficulty, tuple[int, int]]) -> int:
    low, high = ranges[difficulty]
    return random.randint(low, high)


def quantizer(precision: int) -> Decimal:
    return Decimal("1") if precision == 0 else Decimal(f"1e-{precision}")


def floor_decimal(value: Decimal, precision: int) -> Decimal:
    return value.quantize(quantizer(precision), rounding=ROUND_FLOOR)


def format_decimal(value: Decimal, precision: int) -> str:
    return f"{floor_decimal(value, precision):.{precision}f}"


def is_perfect_square(value: int) -> bool:
    root = math.isqrt(value)
    return root * root == value


def make_addition(difficulty: Difficulty, precision: int) -> Problem:
    ranges = {
        "easy": (100, 999),
        "medium": (10_000, 999_999),
        "hard": (1_000_000, 99_999_999),
    }
    a = random_int(difficulty, ranges)
    b = random_int(difficulty, ranges)
    result = a + b
    return Problem(f"{a} + {b} = ", rf"{a} + {b} =", Decimal(result), str(result), "Addition")


def make_subtraction(difficulty: Difficulty, precision: int) -> Problem:
    ranges = {
        "easy": (100, 999),
        "medium": (10_000, 999_999),
        "hard": (1_000_000, 99_999_999),
    }
    a = random_int(difficulty, ranges)
    b = random_int(difficulty, ranges)
    result = a - b
    return Problem(f"{a} - {b} = ", rf"{a} - {b} =", Decimal(result), str(result), "Subtraction")


def make_multiplication(difficulty: Difficulty, precision: int) -> Problem:
    ranges = {
        "easy": (12, 99),
        "medium": (100, 999),
        "hard": (1000, 9999),
    }
    a = random_int(difficulty, ranges)
    b = random_int(difficulty, ranges)
    result = a * b
    return Problem(f"{a} x {b} = ", rf"{a} \times {b} =", Decimal(result), str(result), "Multiplication")


def make_division(difficulty: Difficulty, precision: int) -> Problem:
    numerator_ranges = {
        "easy": (1000, 9999),
        "medium": (100_000, 9_999_999),
        "hard": (10_000_000, 999_999_999),
    }
    divisor_ranges = {
        "easy": (11, 99),
        "medium": (101, 999),
        "hard": (1001, 99_999),
    }
    while True:
        numerator = random_int(difficulty, numerator_ranges)
        divisor = random_int(difficulty, divisor_ranges)
        if numerator % divisor != 0:
            break

    with localcontext() as ctx:
        ctx.prec = max(50, precision + 20)
        result = Decimal(numerator) / Decimal(divisor)

    return Problem(
        f"{numerator} / {divisor} = ",
        rf"\frac{{{numerator}}}{{{divisor}}} =",
        floor_decimal(result, precision),
        format_decimal(result, precision),
        "Division",
        True,
    )


def make_square(difficulty: Difficulty, precision: int) -> Problem:
    ranges = {
        "easy": (20, 99),
        "medium": (100, 999),
        "hard": (1000, 9999),
    }
    n = random_int(difficulty, ranges)
    result = n * n
    return Problem(f"{n}^2 = ", rf"{n}^2 =", Decimal(result), str(result), "Square")


def make_square_root(difficulty: Difficulty, precision: int) -> Problem:
    ranges = {
        "easy": (20, 400),
        "medium": (200, 9999),
        "hard": (1000, 25000),
    }
    while True:
        number = random_int(difficulty, ranges)
        if not is_perfect_square(number):
            break

    with localcontext() as ctx:
        ctx.prec = max(50, precision + 20)
        result = Decimal(number).sqrt()

    return Problem(
        f"sqrt({number}) = ",
        rf"\sqrt{{{number}}} =",
        floor_decimal(result, precision),
        format_decimal(result, precision),
        "Square root",
        True,
    )


def determinant_entry_decimals(precision: int) -> int:
    return 0


def determinant_entry_range(difficulty: Difficulty) -> tuple[int, int]:
    ranges = {
        "easy": (0, 10),
        "medium": (0, 100),
        "hard": (0, 1000),
    }
    return ranges[difficulty]


def make_determinant_entry(difficulty: Difficulty, precision: int) -> Decimal:
    _low, high = determinant_entry_range(difficulty)
    raw = random.randint(-high, high)
    return Decimal(raw)


def make_matrix(size: int, difficulty: Difficulty, precision: int) -> list[list[Decimal]]:
    return [
        [make_determinant_entry(difficulty, precision) for _column in range(size)]
        for _row in range(size)
    ]


def determinant_2x2(matrix: list[list[Decimal]]) -> Decimal:
    return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]


def determinant_3x3(matrix: list[list[Decimal]]) -> Decimal:
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def format_exact_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def determinant_latex(matrix: list[list[Decimal]]) -> str:
    rows = [
        r"\quad".join(format_exact_decimal(value) for value in row)
        for row in matrix
    ]
    return rf"\left|\substack{{{r'\\'.join(rows)}}}\right| ="


def determinant_prompt(matrix: list[list[Decimal]]) -> str:
    rows = ["[" + ", ".join(format_exact_decimal(value) for value in row) + "]" for row in matrix]
    return f"det({'; '.join(rows)}) = "


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


def determinant_matrix_to_png(matrix: tuple[tuple[str, ...], ...], font_size: float = 42.0, dpi: int = 220) -> bytes | None:
    try:
        cache_dir = APP_DIR / "matplotlib_cache"
        cache_dir.mkdir(exist_ok=True)
        os.environ.setdefault("MPLBACKEND", "Agg")
        os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

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
        return buffer.getvalue()
    except Exception:
        return None


def make_determinant_problem(size: int, difficulty: Difficulty, precision: int) -> Problem:
    determinant = determinant_2x2 if size == 2 else determinant_3x3
    while True:
        matrix = make_matrix(size, difficulty, precision)
        result = determinant(matrix)
        if result != 0:
            break

    display_answer = format_exact_decimal(result)
    label = OPERATION_LABELS[f"det{size}"]
    return Problem(
        determinant_prompt(matrix),
        determinant_latex(matrix),
        result,
        display_answer,
        label,
        matrix=tuple(tuple(format_exact_decimal(value) for value in row) for row in matrix),
    )


def make_determinant_2x2(difficulty: Difficulty, precision: int) -> Problem:
    return make_determinant_problem(2, difficulty, precision)


def make_determinant_3x3(difficulty: Difficulty, precision: int) -> Problem:
    return make_determinant_problem(3, difficulty, precision)


GENERATORS: dict[Operation, Callable[[Difficulty, int], Problem]] = {
    "add": make_addition,
    "sub": make_subtraction,
    "mul": make_multiplication,
    "div": make_division,
    "square": make_square,
    "sqrt": make_square_root,
    "det2": make_determinant_2x2,
    "det3": make_determinant_3x3,
}


def parse_approximate_answer(raw: str, precision: int) -> Decimal | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return floor_decimal(Decimal(text), precision)
    except (InvalidOperation, ValueError):
        return None


def parse_exact_answer(raw: str) -> Decimal | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def check_answer(problem: Problem, raw_answer: str, precision: int) -> bool:
    if problem.approximate:
        parsed = parse_approximate_answer(raw_answer, precision)
    else:
        parsed = parse_exact_answer(raw_answer)
    return parsed == problem.answer


def diff_answer_text(user_answer: str, correct_answer: str) -> tuple[list[bool], list[str]]:
    user = user_answer.strip()
    correct = correct_answer.strip()
    wrong = [False] * len(user)
    missing: list[str] = []

    matcher = SequenceMatcher(a=user, b=correct)
    for tag, user_start, user_end, correct_start, correct_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            for index in range(user_start, user_end):
                wrong[index] = True
        elif tag == "insert":
            missing.append(correct[correct_start:correct_end])

    return wrong, missing


def wrong_answer_cli_lines(user_answer: str, correct_answer: str) -> list[str]:
    user = user_answer.strip()
    wrong, missing = diff_answer_text(user, correct_answer)
    marker = "".join("^" if is_wrong else " " for is_wrong in wrong).rstrip()
    lines = [f"Your answer: {user}"]
    if marker:
        lines.append(f"             {marker}")
    if missing:
        lines.append(f"Missing digit(s): {', '.join(missing)}")
    lines.append(f"Correct:     {correct_answer}")
    return lines


def wrong_answer_html(user_answer: str, correct_answer: str) -> str:
    user = user_answer.strip()
    wrong, missing = diff_answer_text(user, correct_answer)
    wrong_style = "color:#a00000; background-color:#ffd6d6; font-weight:700;"
    missing_style = "color:#7a4a00; background-color:#fff0bd; font-weight:700;"
    pieces: list[str] = []

    for char, is_wrong in zip(user, wrong):
        escaped = html.escape(char)
        if is_wrong:
            pieces.append(f'<span style="{wrong_style}">{escaped}</span>')
        else:
            pieces.append(escaped)

    highlighted_user = "".join(pieces) or f'<span style="{wrong_style}">(blank)</span>'
    missing_html = ""
    if missing:
        escaped_missing = html.escape(", ".join(missing))
        missing_html = f'<br>Missing digit(s): <span style="{missing_style}">{escaped_missing}</span>'

    return (
        f'Wrong.<br>Your answer: <span style="font-family:monospace;">{highlighted_user}</span>'
        f"{missing_html}"
        f'<br>Correct: <span style="font-family:monospace;">{html.escape(correct_answer)}</span>'
    )


def choose_operations(raw_operations: list[str] | None, *, default_all: bool) -> list[Operation]:
    if raw_operations is None:
        return list(GENERATORS) if default_all else []
    if "all" in raw_operations:
        return list(GENERATORS)
    return raw_operations


def format_seconds(seconds: float) -> str:
    return f"{seconds:.1f}s"


def accuracy_percent(correct: int, answered: int) -> float:
    return correct / answered * 100 if answered else 0.0


def level_for_score(score: int) -> int:
    return score // 1000 + 1


def points_for_correct_answer(difficulty: Difficulty, elapsed: float, streak: int) -> int:
    base = DIFFICULTY_SCORE[difficulty]
    target = SPEED_TARGET_SECONDS[difficulty]
    speed_bonus = max(0, int((target - elapsed) * 8))
    streak_bonus = min(250, streak * 25)
    return base + speed_bonus + streak_bonus


def make_stats(operations: list[Operation]) -> dict[str, list[int]]:
    return {OPERATION_LABELS[op]: [0, 0] for op in operations}


def default_config() -> dict[str, object]:
    return {
        "count": 20,
        "difficulty": "medium",
        "precision": 2,
        "operations": [],
    }


def default_cumulative_stats() -> dict[str, object]:
    return {
        "sessions": 0,
        "shown": 0,
        "answered": 0,
        "correct": 0,
        "skipped": 0,
        "total_score": 0,
        "best_score": 0,
        "best_streak": 0,
        "by_operation": {
            label: {"answered": 0, "correct": 0}
            for label in OPERATION_LABELS.values()
        },
        "last_session": None,
    }


def load_json_object(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_json_object(path: Path, data: dict[str, object]) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_config() -> dict[str, object]:
    config = default_config()
    saved = load_json_object(CONFIG_PATH)
    if not saved:
        return config

    count = saved.get("count")
    if isinstance(count, int) and count > 0:
        config["count"] = count

    difficulty = saved.get("difficulty")
    if difficulty in DIFFICULTY_LABELS:
        config["difficulty"] = difficulty

    precision = saved.get("precision")
    if isinstance(precision, int) and 0 <= precision <= 12:
        config["precision"] = precision

    operations = saved.get("operations")
    if isinstance(operations, list):
        config["operations"] = [
            op for op in operations if isinstance(op, str) and op in GENERATORS
        ]

    return config


def save_config(config: dict[str, object]) -> None:
    write_json_object(CONFIG_PATH, config)


def load_cumulative_stats() -> dict[str, object]:
    stats = default_cumulative_stats()
    saved = load_json_object(STATS_PATH)
    if not saved:
        return stats

    for key in (
        "sessions",
        "shown",
        "answered",
        "correct",
        "skipped",
        "total_score",
        "best_score",
        "best_streak",
    ):
        value = saved.get(key)
        if isinstance(value, int) and value >= 0:
            stats[key] = value

    saved_by_operation = saved.get("by_operation")
    if isinstance(saved_by_operation, dict):
        by_operation = stats["by_operation"]
        if isinstance(by_operation, dict):
            for label in OPERATION_LABELS.values():
                values = saved_by_operation.get(label)
                if not isinstance(values, dict):
                    continue
                answered = values.get("answered")
                correct = values.get("correct")
                if isinstance(answered, int) and answered >= 0:
                    by_operation[label]["answered"] = answered
                if isinstance(correct, int) and correct >= 0:
                    by_operation[label]["correct"] = correct

    if isinstance(saved.get("last_session"), dict):
        stats["last_session"] = saved["last_session"]

    return stats


def save_cumulative_stats(stats: dict[str, object]) -> None:
    write_json_object(STATS_PATH, stats)


def apply_saved_config_to_args(args: argparse.Namespace, argv: list[str]) -> None:
    config = load_config()

    if not any(arg == "-n" or arg == "--count" or arg.startswith("--count=") for arg in argv):
        args.count = config["count"]

    if not any(arg in {"--easy", "--medium", "--hard"} for arg in argv):
        args.difficulty = config["difficulty"]

    if not any(arg == "-p" or arg == "--precision" or arg.startswith("--precision=") for arg in argv):
        args.precision = config["precision"]

    if not any(arg == "-o" or arg == "--operations" or arg.startswith("--operations=") for arg in argv):
        args.operations = config["operations"]


def run_cli(args: argparse.Namespace) -> int:
    if args.seed is not None:
        random.seed(args.seed)

    operations = choose_operations(args.operations, default_all=True)
    total = args.count
    correct = 0
    skipped = 0
    started_at = time.monotonic()
    per_operation = make_stats(operations)

    print("Mental arithmetic practice started. Type q to quit, or press Enter to skip.")
    print(
        f"Questions: {total}  Difficulty: {DIFFICULTY_LABELS[args.difficulty]}  "
        f"Decimal places: {args.precision}  "
        f"Operations: {', '.join(OPERATION_LABELS[op] for op in operations)}"
    )
    print()

    for index in range(1, total + 1):
        op = random.choice(operations)
        problem = GENERATORS[op](args.difficulty, args.precision)
        question_started_at = time.monotonic()

        raw = input(f"{index:02d}. {problem.prompt}")
        elapsed = time.monotonic() - question_started_at
        normalized = raw.strip().lower()

        if normalized in {"q", "quit", "exit"}:
            print("Stopped.")
            total = index - 1
            break

        if normalized == "":
            skipped += 1
            print(f"Skipped. Answer: {problem.display_answer}")
            continue

        op_stats = per_operation[problem.operation]
        op_stats[1] += 1

        if check_answer(problem, raw, args.precision):
            correct += 1
            op_stats[0] += 1
            print(f"Correct, {format_seconds(elapsed)}")
        else:
            print(f"Wrong, {format_seconds(elapsed)}")
            for line in wrong_answer_cli_lines(raw, problem.display_answer):
                print(line)

    finished_at = time.monotonic()
    answered = sum(op_answered for _, op_answered in per_operation.values())
    accuracy = accuracy_percent(correct, answered)
    duration = finished_at - started_at

    print()
    print("Result")
    print(f"Questions shown: {total}")
    print(f"Correct: {correct}")
    print(f"Skipped: {skipped}")
    print(f"Accuracy: {accuracy:.1f}%")
    print(f"Total time: {format_seconds(duration)}")
    if answered:
        print(f"Average per answered question: {format_seconds(duration / answered)}")

    print()
    print("By operation")
    for label, (op_correct, op_answered) in per_operation.items():
        if op_answered == 0:
            print(f"{label}: no answers")
            continue
        op_accuracy = accuracy_percent(op_correct, op_answered)
        print(f"{label}: {op_correct}/{op_answered} ({op_accuracy:.1f}%)")

    return 0


class TrainerWindowBase:
    """Marker base class used only for type checkers when Qt is imported lazily."""


def run_gui(args: argparse.Namespace) -> int:
    try:
        from PySide6.QtCore import QRectF, Qt, QTimer
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QSizePolicy,
            QSpinBox,
            QToolButton,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        print(f"Qt GUI is the default, but PySide6 is not available: {exc}", file=sys.stderr)
        print("Install PySide6 or run with --cli for terminal mode.", file=sys.stderr)
        return 1

    def latex_to_svg(expression: str) -> bytes | None:
        try:
            cache_dir = APP_DIR / "matplotlib_cache"
            cache_dir.mkdir(exist_ok=True)
            os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
            from matplotlib.mathtext import math_to_image

            configure_latex_fonts()

            buffer = BytesIO()
            math_to_image(
                f"${expression}$",
                buffer,
                dpi=220,
                format="svg",
                color="#111827",
            )
            return buffer.getvalue()
        except Exception:
            return None

    class MathSvgWidget(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.renderer = QSvgRenderer(self)
            self.has_svg = False
            self.pixmap = QPixmap()
            self.setMinimumHeight(136)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        def load_svg(self, svg: bytes) -> bool:
            self.pixmap = QPixmap()
            self.has_svg = self.renderer.load(svg)
            self.update()
            return self.has_svg

        def load_png(self, png: bytes) -> bool:
            pixmap = QPixmap()
            if not pixmap.loadFromData(png, "PNG"):
                return False
            self.has_svg = False
            self.pixmap = pixmap
            self.update()
            return True

        def clear_svg(self) -> None:
            self.has_svg = False
            self.pixmap = QPixmap()
            self.update()

        def paintEvent(self, event) -> None:
            super().paintEvent(event)
            has_pixmap = not self.pixmap.isNull()
            if not self.has_svg and not has_pixmap:
                return

            if self.has_svg:
                natural = self.renderer.defaultSize()
                natural_width = natural.width()
                natural_height = natural.height()
            else:
                natural_width = self.pixmap.width()
                natural_height = self.pixmap.height()

            if natural_width <= 0 or natural_height <= 0:
                aspect = 4.0
            else:
                aspect = natural_width / natural_height

            max_width = min(self.width() * 0.86, 680)
            max_height = min(self.height() * (0.78 if has_pixmap else 0.58), 146 if has_pixmap else 112)
            width = max_width
            height = width / aspect
            if height > max_height:
                height = max_height
                width = height * aspect

            rect = QRectF(
                (self.width() - width) / 2,
                (self.height() - height) / 2,
                width,
                height,
            )

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            if self.has_svg:
                self.renderer.render(painter, rect)
            else:
                self.pixmap.setDevicePixelRatio(1.0)
                painter.drawPixmap(rect, self.pixmap, QRectF(0, 0, natural_width, natural_height))

    class TrainerWindow(QMainWindow, TrainerWindowBase):
        def __init__(self, initial_args: argparse.Namespace) -> None:
            super().__init__()
            self.initial_args = initial_args
            self.operations: list[Operation] = []
            self.per_operation: dict[str, list[int]] = {}
            self.current_problem: Problem | None = None
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
            self.cumulative_stats = load_cumulative_stats()

            self.timer = QTimer(self)
            self.timer.setInterval(250)
            self.timer.timeout.connect(self.update_elapsed)

            self.setWindowTitle("Mental Math Trainer")
            self.resize(860, 560)
            self.setStyleSheet(
                "QMainWindow { background: #f3f5f8; }"
                "QGroupBox { font-weight: 700; border: 1px solid #ccd2dc; "
                "border-radius: 8px; margin-top: 8px; padding-top: 10px; background: #ffffff; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
                "QPushButton { padding: 6px 12px; border-radius: 6px; border: 1px solid #9aa6b2; background: #ffffff; }"
                "QPushButton:hover { background: #eef5ff; }"
                "QPushButton:pressed { background: #d9e9ff; }"
                "QLineEdit { border: 2px solid #7d8da1; border-radius: 7px; padding: 4px 8px; background: #ffffff; }"
                "QLineEdit:focus { border-color: #2f7dd1; }"
            )

            central = QWidget()
            root = QVBoxLayout(central)
            root.setContentsMargins(10, 10, 10, 10)
            root.setSpacing(8)
            self.setCentralWidget(central)

            controls = QWidget()
            controls_layout = QHBoxLayout(controls)
            controls_layout.setContentsMargins(0, 0, 0, 0)
            controls_layout.setSpacing(8)

            self.count_spin = QSpinBox()
            self.count_spin.setRange(1, 999)
            self.count_spin.setValue(initial_args.count)
            self.count_spin.setMaximumWidth(76)

            self.precision_spin = QSpinBox()
            self.precision_spin.setRange(0, 12)
            self.precision_spin.setValue(initial_args.precision)
            self.precision_spin.setMaximumWidth(60)

            self.difficulty_combo = QComboBox()
            for key, label in DIFFICULTY_LABELS.items():
                self.difficulty_combo.addItem(label, key)
            self.difficulty_combo.setCurrentIndex(
                max(0, self.difficulty_combo.findData(initial_args.difficulty))
            )
            self.difficulty_combo.setMaximumWidth(120)

            controls_layout.addWidget(QLabel("Questions"))
            controls_layout.addWidget(self.count_spin)
            controls_layout.addWidget(QLabel("Difficulty"))
            controls_layout.addWidget(self.difficulty_combo)
            controls_layout.addWidget(QLabel("Decimals"))
            controls_layout.addWidget(self.precision_spin)
            controls_layout.addSpacing(8)

            self.operation_checks: dict[Operation, QToolButton] = {}
            selected = set(choose_operations(initial_args.operations, default_all=False))
            for op, label in OPERATION_LABELS.items():
                check = QToolButton()
                check.setText(OPERATION_SYMBOLS[op])
                check.setToolTip(label)
                check.setAccessibleName(label)
                check.setCheckable(True)
                check.setChecked(op in selected)
                check.setFixedSize(38, 30)
                check.setStyleSheet(
                    "QToolButton { font-size: 15px; font-weight: 700; color: #1f2937; "
                    "background: #ffffff; border: 1px solid #b8c2ce; border-radius: 6px; }"
                    "QToolButton:hover { background: #f2f7ff; }"
                    "QToolButton:checked { background: #d7e8ff; border: 1px solid #4a7ebb; color: #102a43; }"
                    "QToolButton:disabled { background: #eef1f5; color: #7a8491; }"
                )
                self.operation_checks[op] = check
                controls_layout.addWidget(check)
            controls_layout.addStretch(1)

            self.start_button = QPushButton("Start")
            self.start_button.clicked.connect(self.start_quiz)
            self.reset_button = QPushButton("Reset")
            self.reset_button.clicked.connect(self.reset_quiz)
            self.start_button.setMinimumWidth(92)
            self.reset_button.setMinimumWidth(92)
            controls_layout.addWidget(self.start_button)
            controls_layout.addWidget(self.reset_button)

            practice_box = QGroupBox("Question")
            practice = QVBoxLayout(practice_box)
            practice.setContentsMargins(18, 18, 18, 18)
            practice.setSpacing(14)
            practice_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            game_row = QHBoxLayout()
            game_row.setSpacing(8)
            self.score_label = QLabel()
            self.streak_label = QLabel()
            self.best_streak_label = QLabel()
            self.level_label = QLabel()
            self.game_labels = [
                self.score_label,
                self.streak_label,
                self.best_streak_label,
                self.level_label,
            ]
            for label in self.game_labels:
                label.setAlignment(Qt.AlignCenter)
                label.setMinimumHeight(36)
                label.setStyleSheet(
                    "QLabel { border-radius: 8px; padding: 5px 10px; "
                    "background: #edf2f7; color: #1f2937; border: 1px solid #cbd5e1; "
                    "font-size: 15px; font-weight: 800; }"
                )
                game_row.addWidget(label)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, initial_args.count)
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(10)
            self.progress_bar.setStyleSheet(
                "QProgressBar { border: none; border-radius: 5px; background: #dbe1ea; }"
                "QProgressBar::chunk { border-radius: 5px; background: #2f7dd1; }"
            )

            self.progress_label = QLabel("Ready")
            self.progress_label.setAlignment(Qt.AlignCenter)

            self.problem_area = QWidget()
            problem_area_layout = QVBoxLayout(self.problem_area)
            problem_area_layout.setContentsMargins(0, 0, 0, 0)
            problem_area_layout.setSpacing(0)
            self.problem_area.setMinimumHeight(136)
            self.problem_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            self.problem_label = QLabel("Press Start")
            self.problem_label.setAlignment(Qt.AlignCenter)
            self.problem_label.setWordWrap(True)
            self.problem_label.setMinimumHeight(136)
            self.problem_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.problem_label.setStyleSheet("font-size: 48px; font-weight: 700;")

            self.problem_svg = MathSvgWidget()
            self.problem_svg.hide()

            problem_area_layout.addWidget(self.problem_label)
            problem_area_layout.addWidget(self.problem_svg)

            self.answer_edit = QLineEdit()
            self.answer_edit.setPlaceholderText("Type your answer")
            self.answer_edit.returnPressed.connect(self.submit_answer)
            self.answer_edit.setMinimumHeight(46)
            self.answer_edit.setStyleSheet("font-size: 24px;")
            self.submit_button = QPushButton("Submit")
            self.submit_button.clicked.connect(self.submit_answer)
            self.skip_button = QPushButton("Skip")
            self.skip_button.clicked.connect(self.skip_problem)
            self.submit_button.setMinimumHeight(46)
            self.skip_button.setMinimumHeight(46)

            answer_row = QHBoxLayout()
            answer_row.addWidget(self.answer_edit, 1)
            answer_row.addWidget(self.submit_button)
            answer_row.addWidget(self.skip_button)

            self.feedback_label = QLabel(" ")
            self.feedback_label.setTextFormat(Qt.RichText)
            self.feedback_label.setWordWrap(True)
            self.feedback_label.setAlignment(Qt.AlignCenter)
            self.feedback_label.setMinimumHeight(74)

            practice.addLayout(game_row)
            practice.addWidget(self.progress_bar)
            practice.addWidget(self.progress_label)
            practice.addWidget(self.problem_area, 1)
            practice.addLayout(answer_row)
            practice.addWidget(self.feedback_label)

            summary_box = QGroupBox("Summary")
            summary = QVBoxLayout(summary_box)
            summary.setContentsMargins(8, 8, 8, 8)
            self.summary_label = QLabel("No active session.")
            self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            summary.addWidget(self.summary_label)
            summary_box.setMaximumHeight(150)

            root.addWidget(controls)
            root.addWidget(practice_box, 1)
            root.addWidget(summary_box)

            self.set_controls_for_active_quiz(False)
            self.update_game_status()

        def selected_operations(self) -> list[Operation]:
            return [
                op
                for op, check in self.operation_checks.items()
                if check.isChecked()
            ]

        def selected_difficulty(self) -> Difficulty:
            return self.difficulty_combo.currentData()

        def current_config(self) -> dict[str, object]:
            return {
                "count": self.count_spin.value(),
                "difficulty": self.selected_difficulty(),
                "precision": self.precision_spin.value(),
                "operations": self.selected_operations(),
            }

        def save_current_config(self) -> None:
            save_config(self.current_config())

        def update_game_status(self) -> None:
            self.score_label.setText(f"Score {self.score}")
            self.streak_label.setText(f"Streak {self.streak}")
            self.best_streak_label.setText(f"Best {self.best_streak}")
            self.level_label.setText(f"Level {level_for_score(self.score)}")

        def set_problem_text(self, text: str) -> None:
            self.problem_svg.clear_svg()
            self.problem_svg.hide()
            self.problem_label.show()
            self.problem_label.setText(text)

        def set_problem_latex(self, problem: Problem) -> None:
            if problem.matrix is not None:
                font_size = 44.0 if len(problem.matrix) <= 2 else 39.0
                png = determinant_matrix_to_png(problem.matrix, font_size=font_size)
                if png is not None and self.problem_svg.load_png(png):
                    self.problem_label.clear()
                    self.problem_label.hide()
                    self.problem_svg.show()
                    return

            svg = latex_to_svg(problem.latex)
            if svg is None:
                self.set_problem_text(problem.prompt)
                return
            if not self.problem_svg.load_svg(svg):
                self.set_problem_text(problem.prompt)
                return
            self.problem_label.clear()
            self.problem_label.hide()
            self.problem_svg.show()

        def set_controls_for_active_quiz(self, active: bool) -> None:
            self.answer_edit.setEnabled(active)
            self.submit_button.setEnabled(active)
            self.skip_button.setEnabled(active)
            self.count_spin.setEnabled(not active)
            self.precision_spin.setEnabled(not active)
            self.difficulty_combo.setEnabled(not active)
            for check in self.operation_checks.values():
                check.setEnabled(not active)

        def start_quiz(self) -> None:
            self.record_session_stats()

            operations = self.selected_operations()
            if not operations:
                QMessageBox.warning(self, "No operations", "Select at least one operation.")
                self.save_current_config()
                return

            if self.initial_args.seed is not None:
                random.seed(self.initial_args.seed)

            self.save_current_config()
            self.operations = operations
            self.per_operation = make_stats(operations)
            self.current_index = 0
            self.correct = 0
            self.skipped = 0
            self.score = 0
            self.streak = 0
            self.best_streak = 0
            self.started_at = time.monotonic()
            self.session_active = True
            self.session_recorded = False
            self.feedback_label.setText(" ")
            self.progress_bar.setRange(0, self.count_spin.value())
            self.progress_bar.setValue(0)
            self.update_game_status()
            self.start_button.setText("Restart")
            self.set_controls_for_active_quiz(True)
            self.timer.start()
            self.next_problem()

        def reset_quiz(self) -> None:
            self.record_session_stats()
            self.save_current_config()
            self.timer.stop()
            self.current_problem = None
            self.current_index = 0
            self.correct = 0
            self.skipped = 0
            self.score = 0
            self.streak = 0
            self.best_streak = 0
            self.session_active = False
            self.session_recorded = False
            self.feedback_label.setText(" ")
            self.set_problem_text("Press Start")
            self.progress_label.setText("Ready")
            self.progress_bar.setRange(0, self.count_spin.value())
            self.progress_bar.setValue(0)
            self.answer_edit.clear()
            self.start_button.setText("Start")
            self.summary_label.setText("No active session.")
            self.set_controls_for_active_quiz(False)
            self.update_game_status()

        def next_problem(self) -> None:
            total = self.count_spin.value()
            if self.current_index >= total:
                self.finish_quiz()
                return

            self.current_index += 1
            operation = random.choice(self.operations)
            self.current_problem = GENERATORS[operation](
                self.selected_difficulty(),
                self.precision_spin.value(),
            )
            self.question_started_at = time.monotonic()
            self.progress_label.setText(f"Question {self.current_index} of {total}")
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(self.current_index - 1)
            self.set_problem_latex(self.current_problem)
            self.answer_edit.clear()
            self.answer_edit.setFocus()
            self.update_summary()

        def submit_answer(self) -> None:
            if self.current_problem is None:
                return

            raw = self.answer_edit.text().strip()
            if not raw:
                self.skip_problem()
                return

            elapsed = time.monotonic() - self.question_started_at
            op_stats = self.per_operation[self.current_problem.operation]
            op_stats[1] += 1

            if check_answer(self.current_problem, raw, self.precision_spin.value()):
                points = points_for_correct_answer(
                    self.selected_difficulty(),
                    elapsed,
                    self.streak,
                )
                self.score += points
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
                self.correct += 1
                op_stats[0] += 1
                self.feedback_label.setText(
                    f'<span style="color:#087443; font-weight:800;">Correct +{points}</span>'
                    f"<br>Streak {self.streak} · {format_seconds(elapsed)}"
                )
                self.update_game_status()
                self.next_problem()
            else:
                self.streak = 0
                self.update_game_status()
                self.feedback_label.setText(
                    f"{wrong_answer_html(raw, self.current_problem.display_answer)}"
                    f"<br>Streak reset · {format_seconds(elapsed)}"
                )
                self.next_problem()

        def skip_problem(self) -> None:
            if self.current_problem is None:
                return
            self.skipped += 1
            self.streak = 0
            self.update_game_status()
            self.feedback_label.setText(
                f"Skipped. Answer: {self.current_problem.display_answer}<br>Streak reset"
            )
            self.next_problem()

        def finish_quiz(self, title: str = "Finished", status: str = "Session complete") -> None:
            self.timer.stop()
            self.current_problem = None
            self.set_problem_text(title)
            self.progress_label.setText(status)
            self.progress_bar.setValue(min(self.current_index, self.count_spin.value()))
            self.answer_edit.clear()
            self.set_controls_for_active_quiz(False)
            self.record_session_stats()
            self.update_summary()

        def update_elapsed(self) -> None:
            if self.started_at:
                self.update_summary()

        def update_summary(self) -> None:
            answered = sum(op_answered for _, op_answered in self.per_operation.values())
            elapsed = time.monotonic() - self.started_at if self.started_at else 0.0
            total = self.count_spin.value()
            best_score = int(self.cumulative_stats.get("best_score", 0))
            all_time_best_streak = int(self.cumulative_stats.get("best_streak", 0))
            lines = [
                f"Shown: {self.current_index}/{total}",
                f"Answered: {answered}",
                f"Correct: {self.correct}",
                f"Skipped: {self.skipped}",
                f"Accuracy: {accuracy_percent(self.correct, answered):.1f}%",
                f"Score: {self.score}",
                f"Level: {level_for_score(self.score)}",
                f"Streak: {self.streak} (session best {self.best_streak})",
                f"Elapsed: {format_seconds(elapsed)}",
                f"All-time best: score {best_score}, streak {all_time_best_streak}",
            ]
            if answered:
                lines.append(f"Average per answered question: {format_seconds(elapsed / answered)}")

            operation_lines = []
            for label, (op_correct, op_answered) in self.per_operation.items():
                if op_answered == 0:
                    operation_lines.append(f"{label}: no answers")
                else:
                    op_accuracy = accuracy_percent(op_correct, op_answered)
                    operation_lines.append(f"{label}: {op_correct}/{op_answered} ({op_accuracy:.1f}%)")

            if operation_lines:
                lines.append("")
                lines.extend(operation_lines)

            self.summary_label.setText("\n".join(lines))

        def record_session_stats(self) -> None:
            if not self.session_active or self.session_recorded:
                return

            answered = sum(op_answered for _, op_answered in self.per_operation.values())
            shown = self.current_index
            if shown == 0 and answered == 0 and self.skipped == 0:
                return

            elapsed = time.monotonic() - self.started_at if self.started_at else 0.0
            stats = self.cumulative_stats
            stats["sessions"] = int(stats.get("sessions", 0)) + 1
            stats["shown"] = int(stats.get("shown", 0)) + shown
            stats["answered"] = int(stats.get("answered", 0)) + answered
            stats["correct"] = int(stats.get("correct", 0)) + self.correct
            stats["skipped"] = int(stats.get("skipped", 0)) + self.skipped
            stats["total_score"] = int(stats.get("total_score", 0)) + self.score
            stats["best_score"] = max(int(stats.get("best_score", 0)), self.score)
            stats["best_streak"] = max(int(stats.get("best_streak", 0)), self.best_streak)

            by_operation = stats.get("by_operation")
            if not isinstance(by_operation, dict):
                by_operation = default_cumulative_stats()["by_operation"]
                stats["by_operation"] = by_operation

            session_ops: dict[str, dict[str, int]] = {}
            for label, (op_correct, op_answered) in self.per_operation.items():
                current = by_operation.setdefault(label, {"answered": 0, "correct": 0})
                if isinstance(current, dict):
                    current["answered"] = int(current.get("answered", 0)) + op_answered
                    current["correct"] = int(current.get("correct", 0)) + op_correct
                session_ops[label] = {"answered": op_answered, "correct": op_correct}

            stats["last_session"] = {
                "shown": shown,
                "answered": answered,
                "correct": self.correct,
                "skipped": self.skipped,
                "accuracy": round(accuracy_percent(self.correct, answered), 2),
                "elapsed_seconds": round(elapsed, 3),
                "score": self.score,
                "level": level_for_score(self.score),
                "best_streak": self.best_streak,
                "difficulty": self.selected_difficulty(),
                "precision": self.precision_spin.value(),
                "operations": self.selected_operations(),
                "by_operation": session_ops,
            }

            save_cumulative_stats(stats)
            self.session_recorded = True
            self.session_active = False

        def closeEvent(self, event) -> None:
            self.record_session_stats()
            self.save_current_config()
            super().closeEvent(event)

    app = QApplication(sys.argv[:1])
    window = TrainerWindow(args)
    window.show()
    return app.exec()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mental arithmetic practice: arithmetic, powers, roots, and determinants."
    )
    parser.add_argument("--cli", action="store_true", help="Use terminal mode instead of the default Qt GUI.")
    parser.add_argument("-n", "--count", type=int, default=20, help="Number of questions, default 20.")

    difficulty = parser.add_mutually_exclusive_group()
    difficulty.add_argument("--easy", action="store_const", dest="difficulty", const="easy", help="Two- and three-digit practice.")
    difficulty.add_argument("--medium", action="store_const", dest="difficulty", const="medium", help="Default; larger integers and three-digit multiplication/division.")
    difficulty.add_argument("--hard", action="store_const", dest="difficulty", const="hard", help="Large numbers, four-digit products, and large roots.")
    parser.set_defaults(difficulty="medium")

    parser.add_argument(
        "-p",
        "--precision",
        type=int,
        default=2,
        help="Decimal places required for division and square root answers, default 2.",
    )
    parser.add_argument(
        "-o",
        "--operations",
        nargs="+",
        choices=("all", *GENERATORS.keys()),
        default=None,
        help="Operations: all/add/sub/mul/div/square/sqrt/det2/det3. GUI uses saved config or none; CLI defaults to all.",
    )
    parser.add_argument("--seed", type=int, help="Fixed random seed for repeatable sessions.")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.count <= 0:
        parser.error("--count must be greater than 0.")
    if args.precision < 0:
        parser.error("--precision must be at least 0.")
    if args.precision > 12:
        parser.error("--precision is too large for mental arithmetic; use 0 to 12.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.cli:
        apply_saved_config_to_args(args, sys.argv[1:])
    validate_args(parser, args)
    if args.cli:
        return run_cli(args)
    return run_gui(args)


if __name__ == "__main__":
    raise SystemExit(main())
