# prompt_engineer.py
# Requires: PyQt6  (pip install PyQt6)
# Python 3.9+

from __future__ import annotations
import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QCheckBox, QFileDialog, QGroupBox,
    QGridLayout, QMessageBox, QStatusBar, QScrollArea, QLineEdit,
    QComboBox
)

# ------------------------------------------------------------
# Original helpers (kept verbatim to preserve behavior/wording)
# ------------------------------------------------------------

def add_thinking(string=''):
    return string + 'Show all your steps and your thinking process'

def show_me_your_skills(string=''):
    return string + 'Show all you calculations'

def more_details(string=''):
    return string + 'Be as detailed as possible'

def self_critique(string=''):
    return string + "In the end, critique your answer and improve it"

def shadow_clones(string=''):
    return string + "Generate three different answers and pick the best."

def expertize(string=''):
    return 'you are an expert in the question that will be asked.  ' + string

def presioning(string=''):
    return string + 'Be precise and avoid making assumptions.'

def do_not_lie(string=''):
    return string + 'Do not tell information you do not know. If there is something you do not know about the question, clearly say it to the user'

def trasparency(string=''):
    return string + 'Clearly state any limitations or areas of uncertainty'


# ------------------------------------------------------------
# Previously added helpers (appenders & prependers)
# ------------------------------------------------------------

def format_json(string=''):
    return string + 'Format the final answer as a JSON object with clear keys and no extra prose.'

def cite_sources(string=''):
    return string + 'Cite all sources with links and a one-line justification for each.'

def ask_questions_first(string=''):
    return string + 'Before answering, ask any clarifying questions needed; if none are needed, proceed.'

def list_assumptions(string=''):
    return string + 'List any assumptions you had to make to answer.'

def edge_cases(string=''):
    return string + 'Consider edge cases and explain how they impact the solution.'

def provide_examples(string=''):
    return string + 'Include at least two concrete, realistic examples.'

def outline_then_answer(string=''):
    return string + 'First provide a short outline of your plan, then deliver the full answer.'

def alternatives_and_tradeoffs(string=''):
    return string + 'Propose at least two alternative approaches and compare their trade-offs.'

def time_awareness(string=''):
    return string + 'State the current date and time zone you assume, and note any time-sensitive caveats.'

def rubric_self_eval(string=''):
    return string + 'At the end, evaluate your answer against a brief rubric and score each criterion from 1–5.'

def action_items(string=''):
    return string + 'Finish with a numbered list of next actions a user can take.'

def constraints_first(string=''):
    return string + 'Begin by explicitly listing constraints, requirements, and non-goals.'

def definitions_glossary(string=''):
    return string + 'Define key terms in a short glossary before proceeding.'

def test_plan(string=''):
    return string + 'Provide a lightweight test/validation plan to verify the solution works as intended.'

def technical_writer_persona(string=''):
    return 'You are a meticulous technical writer who communicates clearly and concisely. ' + string


# ------------------------------------------------------------
# NEW: extra roles + new categories (more options)
# ------------------------------------------------------------

# Roles / personas (prepend)
def socratic_tutor(string=''):
    return 'You are a Socratic tutor who guides with questions and short hints. ' + string

def product_manager(string=''):
    return 'You are a pragmatic product manager focused on user impact, scope, and trade-offs. ' + string

def data_scientist(string=''):
    return 'You are a data scientist skilled in statistics and experiment design. ' + string

def software_architect(string=''):
    return 'You are a seasoned software architect emphasizing modular design and scalability. ' + string

def security_auditor(string=''):
    return 'You are a security auditor identifying risks and mitigations. ' + string

def copywriter_persona(string=''):
    return 'You are a persuasive copywriter who writes clearly and concisely. ' + string

def ux_researcher(string=''):
    return 'You are a UX researcher focusing on user needs and usability. ' + string

def teacher_grade5(string=''):
    return 'You are a patient teacher explaining concepts to a 5th-grade student. ' + string

def legal_analyst_disclaimer(string=''):
    return 'You are a legal analyst providing educational information (not legal advice). ' + string

def sre_devops(string=''):
    return 'You are an SRE/DevOps engineer focusing on reliability and observability. ' + string

def data_engineer(string=''):
    return 'You are a data engineer optimizing reliable data pipelines and schemas. ' + string

def financial_analyst_disclaimer(string=''):
    return 'You are a financial analyst providing educational information (not financial advice). ' + string

def game_designer(string=''):
    return 'You are a game designer focusing on mechanics, balance, and player motivation. ' + string

def math_coach(string=''):
    return 'You are a math coach who explains step-by-step and checks understanding. ' + string

def interviewer(string=''):
    return 'You are an interviewer who asks probing, structured questions. ' + string


# Audience & context (prepend)
def audience_beginner(string=''):
    return 'Assume the audience are beginners with no prior knowledge. ' + string

def audience_advanced(string=''):
    return 'Assume the audience is advanced and prefers concise technical depth. ' + string

def audience_executive(string=''):
    return 'Assume an executive audience; prioritize outcomes, risks, and next steps. ' + string

def audience_global(string=''):
    return 'Write for a global audience and avoid region-specific jargon. ' + string

def audience_plain_english(string=''):
    return 'Use simple, plain English suitable for non-native readers. ' + string


# Tone & style (append)
def tone_concise_bullets(string=''):
    return string + 'Answer concisely using bullet points.'

def tone_friendly(string=''):
    return string + 'Use a friendly, supportive tone.'

def tone_academic(string=''):
    return string + 'Use a formal, academic tone with citations where appropriate.'

def tone_professional(string=''):
    return string + 'Use a neutral, professional tone.'

def tone_numbered_steps(string=''):
    return string + 'Organize the answer as numbered steps.'

def tone_confident(string=''):
    return string + 'Adopt a confident and assertive tone while remaining factual.'


# Output & structure (append)
def tldr_first(string=''):
    return string + 'Start with a 2–3 sentence TL;DR summary, then provide details.'

def markdown_table(string=''):
    return string + 'Include a concise Markdown table summarizing key points.'

def section_headers(string=''):
    return string + 'Use clear section headers: Overview, Approach, Examples, Caveats, Next Steps.'

def faq_section(string=''):
    return string + 'End with a short FAQ section with 3–5 Q&A pairs.'

def star_format(string=''):
    return string + 'When describing experiences, use the STAR format (Situation, Task, Action, Result).'

def mece_structure(string=''):
    return string + 'Organize points using a MECE structure (mutually exclusive, collectively exhaustive).'


# Safety & QA (append)
def bias_check(string=''):
    return string + 'Identify potential biases or blind spots and note how you mitigated them.'

def risk_register(string=''):
    return string + 'List key risks and mitigation strategies.'

def security_considerations(string=''):
    return string + 'Include security considerations and safe usage guidelines.'

def license_note(string=''):
    return string + 'When including code or data, note relevant licenses if known.'


# Code & data requirements (append)
def runnable_code_snippet(string=''):
    return string + 'Include a minimal runnable code snippet with inline comments.'

def pseudocode_first(string=''):
    return string + 'Before code, give short pseudocode.'

def complexity_analysis(string=''):
    return string + 'Include time and space complexity where applicable.'

def unit_tests(string=''):
    return string + 'Provide simple unit test examples or test cases.'

def data_schema(string=''):
    return string + 'If data is involved, include a minimal schema and field descriptions.'


# ------------------------------------------------------------
# Option registries (key, label, func, tooltip)
# ------------------------------------------------------------

ROLES = [
    ("role_expert", "Expert role", expertize, "Prepend: 'you are an expert in the question that will be asked.'"),
    ("role_tech_writer", "Technical writer", technical_writer_persona, "Prepend: meticulous technical writer persona"),
    ("role_socratic", "Socratic tutor", socratic_tutor, "Prepend: guides with questions and hints"),
    ("role_pm", "Product manager", product_manager, "Prepend: user impact, scope, trade-offs"),
    ("role_ds", "Data scientist", data_scientist, "Prepend: statistics & experiment design"),
    ("role_arch", "Software architect", software_architect, "Prepend: modularity & scalability"),
    ("role_sec", "Security auditor", security_auditor, "Prepend: risks & mitigations"),
    ("role_copy", "Copywriter", copywriter_persona, "Prepend: persuasive, concise messaging"),
    ("role_ux", "UX researcher", ux_researcher, "Prepend: user needs & usability"),
    ("role_teacher", "Teacher (5th grade)", teacher_grade5, "Prepend: explain for a 5th grader"),
    ("role_legal", "Legal analyst (educational)", legal_analyst_disclaimer, "Prepend: not legal advice"),
    ("role_sre", "SRE/DevOps", sre_devops, "Prepend: reliability & observability"),
    ("role_de", "Data engineer", data_engineer, "Prepend: data pipelines & schemas"),
    ("role_fa", "Financial analyst (educational)", financial_analyst_disclaimer, "Prepend: not financial advice"),
    ("role_gd", "Game designer", game_designer, "Prepend: mechanics & player motivation"),
    ("role_math", "Math coach", math_coach, "Prepend: step-by-step explanations"),
    ("role_interviewer", "Interviewer", interviewer, "Prepend: asks probing, structured questions"),
]

AUDIENCE = [
    ("aud_beg", "Beginner audience", audience_beginner, "Prepend: assume no prior knowledge"),
    ("aud_adv", "Advanced audience", audience_advanced, "Prepend: concise, technical depth"),
    ("aud_exec", "Executive audience", audience_executive, "Prepend: outcomes, risks, next steps"),
    ("aud_global", "Global audience", audience_global, "Prepend: avoid region-specific jargon"),
    ("aud_plain", "Plain English", audience_plain_english, "Prepend: simple, accessible language"),
]

AUGMENTATIONS = [
    ("aug_think", "Add thinking (step-by-step)", add_thinking, "Append: 'Show all your steps...'"),
    ("aug_calc", "Show calculations", show_me_your_skills, "Append: 'Show all you calculations'"),
    ("aug_more", "More details", more_details, "Append: 'Be as detailed as possible'"),
    ("aug_crit", "Self-critique", self_critique, "Append: 'In the end, critique your answer...'"),
    ("aug_clones", "Shadow clones (3 answers, pick best)", shadow_clones, "Append: 'Generate three different answers...'"),
    ("aug_prec", "Precision (avoid assumptions)", presioning, "Append: 'Be precise and avoid making assumptions.'"),
    ("aug_truth", "Do not lie / admit uncertainty", do_not_lie, "Append: 'Do not tell information you do not know...'"),
    ("aug_transp", "Transparency", trasparency, "Append: 'Clearly state any limitations or areas of uncertainty'"),
    ("aug_json", "JSON output format", format_json, "Append: format result as JSON object"),
    ("aug_cite", "Cite sources w/ links", cite_sources, "Append: cite sources + 1-line justification"),
    ("aug_ask", "Ask clarifying Qs first", ask_questions_first, "Append: ask clarifying questions first"),
    ("aug_assume", "List assumptions", list_assumptions, "Append: list any assumptions"),
    ("aug_edge", "Edge cases", edge_cases, "Append: consider edge cases"),
    ("aug_examples", "Provide examples", provide_examples, "Append: include at least two examples"),
    ("aug_outline", "Outline then answer", outline_then_answer, "Append: outline first, then full answer"),
    ("aug_alts", "Alternatives & trade-offs", alternatives_and_tradeoffs, "Append: propose alternatives & compare"),
    ("aug_time", "Time awareness", time_awareness, "Append: state current date/timezone assumptions"),
    ("aug_rubric", "Rubric self-eval", rubric_self_eval, "Append: evaluate your answer with a rubric"),
    ("aug_actions", "Actionable next steps", action_items, "Append: numbered next actions"),
    ("aug_constraints", "Constraints & non-goals first", constraints_first, "Append: list constraints and non-goals"),
    ("aug_glossary", "Definitions glossary", definitions_glossary, "Append: short glossary of key terms"),
    ("aug_test", "Test/validation plan", test_plan, "Append: lightweight test/validation plan"),
]

TONE_STYLE = [
    ("tone_bullets", "Concise bullet points", tone_concise_bullets, "Append: answer using bullets"),
    ("tone_friendly", "Friendly tone", tone_friendly, "Append: friendly, supportive tone"),
    ("tone_acad", "Academic tone", tone_academic, "Append: formal, academic tone"),
    ("tone_prof", "Professional tone", tone_professional, "Append: neutral, professional tone"),
    ("tone_steps", "Numbered steps", tone_numbered_steps, "Append: organize as numbered steps"),
    ("tone_conf", "Confident tone", tone_confident, "Append: confident, assertive tone"),
]

OUTPUT_STRUCT = [
    ("out_tldr", "TL;DR first", tldr_first, "Append: brief TL;DR before details"),
    ("out_table", "Markdown table", markdown_table, "Append: include a summary table"),
    ("out_headers", "Section headers", section_headers, "Append: headers structure"),
    ("out_faq", "FAQ section", faq_section, "Append: close with a short FAQ"),
    ("out_star", "STAR format", star_format, "Append: STAR structure"),
    ("out_mece", "MECE structure", mece_structure, "Append: MECE organization"),
]

SAFETY_QA = [
    ("qa_bias", "Bias check", bias_check, "Append: identify potential biases"),
    ("qa_risks", "Risk register", risk_register, "Append: key risks + mitigations"),
    ("qa_sec", "Security considerations", security_considerations, "Append: security & safe use notes"),
    ("qa_license", "License note", license_note, "Append: mention licenses if known"),
]

CODE_DATA = [
    ("code_run", "Runnable code snippet", runnable_code_snippet, "Append: minimal runnable code with comments"),
    ("code_pseudo", "Pseudocode first", pseudocode_first, "Append: give pseudocode before code"),
    ("code_complex", "Complexity analysis", complexity_analysis, "Append: time/space complexity"),
    ("code_tests", "Unit tests", unit_tests, "Append: simple unit tests or cases"),
    ("code_schema", "Data schema", data_schema, "Append: minimal schema & field descriptions"),
]


# ------------------------------------------------------------
# Utilities: persistence of popularity & recents
# ------------------------------------------------------------

STATE_PATH = os.path.join(str(Path.home()), ".prompt_builder_state.json")
DEFAULT_STATE = {"popular": {}, "recent": [], "favorites": []}  # recent is list of lists of keys

def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_STATE.copy()

def save_state(state):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


# ------------------------------------------------------------
# Main window
# ------------------------------------------------------------

class PromptBuilder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prompt Engineering Builder — Dark Mode")
        self.setMinimumSize(1200, 760)
        self.setWindowIcon(QIcon())

        # Registry: key -> (checkbox, func, label)
        self.key_to_checkbox = {}
        self.key_to_func = {}
        self.key_to_label = {}
        self.key_to_chips = {}  # key -> list[QPushButton] mirrors for chip buttons

        # Load persisted state
        self.state = load_state()

        # Central layout
        root = QHBoxLayout()
        host = QWidget()
        host.setLayout(root)
        self.setCentralWidget(host)

        # Left: controls in scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll, 1)

        controls_host = QWidget()
        self.scroll.setWidget(controls_host)
        controls_col = QVBoxLayout(controls_host)
        controls_col.setSpacing(8)

        # Search & Presets row
        top_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search options… (filters all lists)")
        self.search_edit.textChanged.connect(self.apply_filter)
        top_row.addWidget(self.search_edit, 1)

        self.preset_box = QComboBox()
        self.preset_box.addItems([
            "Preset…",
            "Core Writing",
            "Coding",
            "Safety/QA",
            "Concise Executive",
            "Beginner Teaching",
        ])
        btn_apply_preset = QPushButton("Apply")
        btn_apply_preset.clicked.connect(self.apply_preset)
        top_row.addWidget(self.preset_box)
        top_row.addWidget(btn_apply_preset)
        controls_col.addLayout(top_row)

        # Quick chips: Recent & Popular
        self.recent_group = QGroupBox("Recently Used (click to toggle)")
        self.recent_layout = QGridLayout(self.recent_group)
        controls_col.addWidget(self.recent_group)

        self.popular_group = QGroupBox("Most Popular (click to toggle)")
        self.popular_layout = QGridLayout(self.popular_group)
        controls_col.addWidget(self.popular_group)

        # Base prompt
        base_group = QGroupBox("Base Prompt")
        base_layout = QVBoxLayout(base_group)
        self.base_edit = QTextEdit()
        self.base_edit.setPlaceholderText("Type your base prompt here…")
        self.base_edit.textChanged.connect(self.update_preview)
        base_layout.addWidget(self.base_edit)
        controls_col.addWidget(base_group, 0)

        # Builders
        self.roles_checks = []
        controls_col.addWidget(self._make_group("Roles / Personas (prepended in listed order)",
                                                ROLES, self.roles_checks, cols=2))
        self.audience_checks = []
        controls_col.addWidget(self._make_group("Audience & Context (prepended in listed order)",
                                                AUDIENCE, self.audience_checks, cols=2))
        self.aug_checks = []
        controls_col.addWidget(self._make_group("Augmentations (appended in listed order)",
                                                AUGMENTATIONS, self.aug_checks, cols=2))
        self.tone_checks = []
        controls_col.addWidget(self._make_group("Tone & Style (appended in listed order)",
                                                TONE_STYLE, self.tone_checks, cols=2))
        self.output_checks = []
        controls_col.addWidget(self._make_group("Output & Structure (appended in listed order)",
                                                OUTPUT_STRUCT, self.output_checks, cols=2))
        self.safety_checks = []
        controls_col.addWidget(self._make_group("Safety & QA (appended in listed order)",
                                                SAFETY_QA, self.safety_checks, cols=2))
        self.code_checks = []
        controls_col.addWidget(self._make_group("Code & Data Requirements (appended in listed order)",
                                                CODE_DATA, self.code_checks, cols=2))

        # Buttons
        button_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(self.select_all)
        btn_none = QPushButton("Clear All")
        btn_none.clicked.connect(self.clear_all)
        btn_copy = QPushButton("Copy")
        btn_copy.clicked.connect(self.copy_to_clipboard_and_record)
        btn_save = QPushButton("Save…")
        btn_save.clicked.connect(self.save_to_file_and_record)
        btn_use = QPushButton("Mark As Used")
        btn_use.setToolTip("Record current selection as a use (updates Recent & Popular)")
        btn_use.clicked.connect(self.record_usage)
        for b in (btn_all, btn_none, btn_copy, btn_save, btn_use):
            button_row.addWidget(b)
        controls_col.addLayout(button_row)

        # Right: preview
        right = QVBoxLayout()
        root.addLayout(right, 1)

        header_row = QHBoxLayout()
        preview_label = QLabel("Preview (read-only)")
        preview_label.setStyleSheet("font-weight: 600;")
        header_row.addWidget(preview_label)
        header_row.addStretch(1)
        self.theme_toggle = QPushButton("Light Theme")
        self.theme_toggle.setCheckable(True)
        self.theme_toggle.clicked.connect(self.toggle_theme)
        header_row.addWidget(self.theme_toggle)
        right.addLayout(header_row)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Your composed prompt will appear here…")
        right.addWidget(self.preview, 1)

        tip = QLabel(
            "Note: Some models won’t reveal internal step-by-step reasoning. "
            "If you get refusals, try structured outlines, rationales, or numbered steps instead."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #9aa0a6;")
        right.addWidget(tip)

        self.setStatusBar(QStatusBar())
        self.apply_dark_theme()  # default to dark
        self.update_preview()
        self.refresh_quick_chips()

        # Menu (small conveniences)
        self._build_menu()

        # Styling
        self.setStyleSheet(self._base_stylesheet())

    # -------------------------------
    # UI Construction helpers
    # -------------------------------
    def _build_menu(self):
        menu = self.menuBar().addMenu("&File")
        act_copy = QAction("Copy", self)
        act_copy.triggered.connect(self.copy_to_clipboard_and_record)
        act_save = QAction("Save…", self)
        act_save.triggered.connect(self.save_to_file_and_record)
        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        menu.addActions([act_copy, act_save, act_exit])

        view = self.menuBar().addMenu("&View")
        act_dark = QAction("Dark Mode", self, checkable=True, checked=True)
        act_dark.triggered.connect(lambda checked: self.apply_dark_theme() if checked else self.apply_light_theme())
        view.addAction(act_dark)

    def _make_group(self, title, items, store_list, cols=2) -> QGroupBox:
        group = QGroupBox(title)
        grid = QGridLayout(group)
        for i, (key, label, func, tip) in enumerate(items):
            cb = QCheckBox(label)
            cb.setToolTip(tip)
            cb.stateChanged.connect(self.update_preview)
            store_list.append((cb, func, key, label))
            self.key_to_checkbox[key] = cb
            self.key_to_func[key] = func
            self.key_to_label[key] = label
            row = i // cols
            col = i % cols
            grid.addWidget(cb, row, col)
        return group

    def _base_stylesheet(self) -> str:
        # Subtle, modern dark UI with pill buttons ("chips")
        return """
        QGroupBox {
            font-weight: 600;
            border: 1px solid #2a2e35;
            border-radius: 10px;
            margin-top: 10px;
            padding: 10px 10px 8px 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0px 4px 0px 4px;
            color: #e8eaed;
        }
        QTextEdit, QLineEdit, QComboBox {
            border: 1px solid #30343a;
            border-radius: 8px;
            padding: 8px;
            font-size: 14px;
            background: #1f2227;
            color: #e8eaed;
        }
        QPushButton {
            border: 1px solid #30343a;
            border-radius: 10px;
            padding: 7px 12px;
            background: #2a2e35;
            color: #e8eaed;
        }
        QPushButton:hover { border-color: #4b5563; }
        QPushButton:checked {
            background: #3b82f6;
            border-color: #3b82f6;
            color: white;
        }
        QCheckBox {
            color: #e8eaed;
            spacing: 8px;
        }
        QStatusBar { color: #cbd5e1; }
        QMenuBar { background: #1f2227; color: #e8eaed; }
        QMenu { background: #1f2227; color: #e8eaed; border: 1px solid #30343a; }
        """

    def apply_dark_theme(self):
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#15181c"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#1f2227"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1f2227"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1f2227"))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#2a2e35"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#e8eaed"))
        pal.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#3b82f6"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        QApplication.instance().setPalette(pal)
        self.theme_toggle.setChecked(True)
        self.theme_toggle.setText("Light Theme")

    def apply_light_theme(self):
        QApplication.instance().setPalette(QApplication.style().standardPalette())
        self.theme_toggle.setChecked(False)
        self.theme_toggle.setText("Dark Theme")

    def toggle_theme(self):
        if self.theme_toggle.isChecked():
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

    # -------------------------------
    # Build final prompt
    # -------------------------------
    def build_prompt(self) -> str:
        base = self.base_edit.toPlainText()

        def ensure_space(s: str) -> str:
            return (s.rstrip() + " ") if s and not s.endswith((" ", "\n")) else s

        s = base

        # Prepend groups in order: Roles -> Audience
        for cb, func, key, _ in self.roles_checks:
            if cb.isChecked():
                s = func(s)
        for cb, func, key, _ in self.audience_checks:
            if cb.isChecked():
                s = func(s)

        # Append groups in order: Augment -> Tone -> Output -> Safety -> Code
        for group in (self.aug_checks, self.tone_checks, self.output_checks,
                      self.safety_checks, self.code_checks):
            for cb, func, key, _ in group:
                if cb.isChecked():
                    s = ensure_space(s)
                    s = func(s)

        return s.strip()

    # -------------------------------
    # Quick chips (Recent/Popular)
    # -------------------------------
    def refresh_quick_chips(self):
        # Clear layouts
        def clear_layout(layout: QGridLayout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

        clear_layout(self.recent_layout)
        clear_layout(self.popular_layout)

        recent_keys = self._compute_recent_keys(limit=10)
        popular_keys = self._compute_popular_keys(limit=10)

        self._add_chip_row(self.recent_layout, recent_keys)
        self._add_chip_row(self.popular_layout, popular_keys)

    def _compute_recent_keys(self, limit=10):
        # Flatten recent lists newest->oldest, keep unique
        seen = set()
        result = []
        for key_list in reversed(self.state.get("recent", [])):
            for k in key_list:
                if k in self.key_to_checkbox and k not in seen:
                    seen.add(k)
                    result.append(k)
                    if len(result) >= limit:
                        return result
        return result

    def _compute_popular_keys(self, limit=10):
        pop = self.state.get("popular", {})
        sorted_keys = sorted(
            [k for k in pop if k in self.key_to_checkbox],
            key=lambda k: pop.get(k, 0),
            reverse=True
        )
        return sorted_keys[:limit]

    def _add_chip_row(self, layout: QGridLayout, keys: list[str]):
        self.key_to_chips.setdefault("__all__", [])
        for i, key in enumerate(keys):
            label = self.key_to_label.get(key, key)
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(self.key_to_checkbox[key].isChecked())
            btn.clicked.connect(lambda checked, kk=key: self._chip_clicked(kk, checked))
            # Track chips to keep them synced when underlying checkbox toggles elsewhere
            self.key_to_chips.setdefault(key, []).append(btn)
            row = i // 3
            col = i % 3
            layout.addWidget(btn, row, col)

        # Keep chips synced with checkbox state
        for key in keys:
            cb = self.key_to_checkbox[key]
            cb.stateChanged.connect(lambda _state, kk=key: self._sync_chips(kk))

    def _chip_clicked(self, key: str, checked: bool):
        cb = self.key_to_checkbox.get(key)
        if cb:
            cb.setChecked(checked)

    def _sync_chips(self, key: str):
        for btn in self.key_to_chips.get(key, []):
            btn.setChecked(self.key_to_checkbox[key].isChecked())

    # -------------------------------
    # Search / filter
    # -------------------------------
    def apply_filter(self, text: str):
        t = text.strip().lower()
        def filt(cb: QCheckBox, label: str):
            if not t:
                cb.setVisible(True)
                return
            cb.setVisible(t in label.lower())

        for cb, func, key, label in (
            self.roles_checks + self.audience_checks + self.aug_checks +
            self.tone_checks + self.output_checks + self.safety_checks + self.code_checks
        ):
            filt(cb, label)

    # -------------------------------
    # Presets
    # -------------------------------
    def apply_preset(self):
        name = self.preset_box.currentText()
        presets = {
            "Core Writing": [
                "aug_constraints", "aug_outline", "tone_bullets", "out_tldr",
                "out_headers", "aug_examples", "aug_actions", "aug_transp",
                "aug_prec", "aug_ask"
            ],
            "Coding": [
                "role_arch", "role_sre",
                "code_pseudo", "code_run", "code_tests", "code_complex",
                "aug_edge", "aug_constraints", "out_headers"
            ],
            "Safety/QA": [
                "qa_bias", "qa_risks", "qa_sec", "qa_license",
                "aug_transp", "aug_prec", "aug_assume"
            ],
            "Concise Executive": [
                "aud_exec", "tone_prof", "out_tldr", "aug_actions", "out_headers"
            ],
            "Beginner Teaching": [
                "role_teacher", "aud_beg", "tone_steps", "aug_examples", "aug_ask"
            ],
        }
        if name in presets:
            self.clear_all()
            for key in presets[name]:
                if key in self.key_to_checkbox:
                    self.key_to_checkbox[key].setChecked(True)
            self.statusBar().showMessage(f"Applied preset: {name}", 3000)

    # -------------------------------
    # Actions
    # -------------------------------
    def update_preview(self):
        self.preview.setPlainText(self.build_prompt())

    def select_all(self):
        for cb, *_ in (self.roles_checks + self.audience_checks + self.aug_checks +
                       self.tone_checks + self.output_checks + self.safety_checks + self.code_checks):
            cb.setChecked(True)

    def clear_all(self):
        for cb, *_ in (self.roles_checks + self.audience_checks + self.aug_checks +
                       self.tone_checks + self.output_checks + self.safety_checks + self.code_checks):
            cb.setChecked(False)

    def copy_to_clipboard_and_record(self):
        final = self.build_prompt()
        QApplication.clipboard().setText(final)
        self.statusBar().showMessage("Prompt copied to clipboard.", 3000)
        self.record_usage()

    def save_to_file_and_record(self):
        final = self.build_prompt()
        if not final:
            QMessageBox.information(self, "Nothing to save", "The composed prompt is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Prompt", "prompt.txt", "Text Files (*.txt);;All Files (*)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(final)
                self.statusBar().showMessage(f"Saved: {path}", 4000)
                self.record_usage()
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Could not save file:\n{e}")

    def record_usage(self):
        # Count checked options and push to recent list
        checked_keys = []
        for group in (self.roles_checks, self.audience_checks, self.aug_checks,
                      self.tone_checks, self.output_checks, self.safety_checks, self.code_checks):
            for cb, func, key, _ in group:
                if cb.isChecked():
                    checked_keys.append(key)

        # Update popularity counts
        pop = self.state.setdefault("popular", {})
        for k in checked_keys:
            pop[k] = pop.get(k, 0) + 1

        # Update recent (cap to last 25 sessions)
        rec = self.state.setdefault("recent", [])
        if checked_keys:
            rec.append(checked_keys)
            if len(rec) > 25:
                del rec[0]

        save_state(self.state)
        self.refresh_quick_chips()
        self.statusBar().showMessage("Usage recorded (Recent & Popular updated).", 3000)


# ------------------------------------------------------------
# App bootstrap
# ------------------------------------------------------------

def main():
    import sys
    app = QApplication(sys.argv)
    win = PromptBuilder()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
