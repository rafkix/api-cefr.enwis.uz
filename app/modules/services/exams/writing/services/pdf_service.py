import io
import os
import html
import uuid
from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader


class PDFService:
    def __init__(self):
        self.logo_path = "static/logo.png"
        self.organization_name = "ENWIS EDUCATION CENTER"
        self.watermark_text = "ENWIS.UZ"

    # -------------------------------------------------------
    # HEADER + FOOTER + WATERMARK
    # -------------------------------------------------------
    def _draw_header_footer(self, canvas_obj, doc, user_name: str):
        canvas_obj.saveState()
        width, height = A4

        # WATERMARK
        canvas_obj.setFillColorRGB(0.94, 0.94, 0.94)
        canvas_obj.setFont("Helvetica-Bold", 60)
        canvas_obj.saveState()
        canvas_obj.translate(width / 2, height / 2)
        canvas_obj.rotate(35)
        canvas_obj.drawCentredString(0, 0, self.watermark_text)
        canvas_obj.restoreState()

        # HEADER strip
        canvas_obj.setFillColor(colors.HexColor("#0f172a"))
        canvas_obj.rect(0, height - 22 * mm, width, 22 * mm, stroke=0, fill=1)

        # LOGO
        if os.path.exists(self.logo_path):
            logo = ImageReader(self.logo_path)
            canvas_obj.drawImage(
                logo,
                15 * mm,
                height - 18 * mm,
                width=22 * mm,
                height=12 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )

        # Org name (right)
        canvas_obj.setFont("Helvetica-Bold", 11)
        canvas_obj.setFillColor(colors.white)
        canvas_obj.drawRightString(
            width - 15 * mm,
            height - 14 * mm,
            self.organization_name,
        )

        # Divider lines
        canvas_obj.setStrokeColor(colors.HexColor("#e2e8f0"))
        canvas_obj.setLineWidth(0.8)
        canvas_obj.line(15 * mm, height - 22 * mm, width - 15 * mm, height - 22 * mm)
        canvas_obj.line(15 * mm, 16 * mm, width - 15 * mm, 16 * mm)

        # Footer text
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(15 * mm, 8.5 * mm, "enwis.uz • Official Report")
        canvas_obj.drawRightString(width - 15 * mm, 8.5 * mm, f"Page {doc.page}")

        canvas_obj.restoreState()

    # -------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------
    def _safe_paragraph(self, text: str, style):
        safe = html.escape(text or "").replace("\n", "<br/>")
        return Paragraph(safe, style)

    def _fmt_dt(self, dt) -> str:
        if not dt:
            return datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        try:
            if isinstance(dt, str):
                return dt.replace("T", " ")[:16]
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(dt)

    def _get_user_name(self, result) -> str:
        user = getattr(result, "user", None)
        profile = getattr(user, "profile", None) if user else None

        full_name = getattr(profile, "full_name", None) if profile else None
        username = getattr(profile, "username", None) if profile else None

        return (full_name or username or "Candidate").strip()

    def _get_exam_title(self, result) -> str:
        exam = getattr(result, "exam", None)
        return (
            getattr(exam, "title", None)
            or getattr(result, "exam_id", None)
            or "Writing Exam"
        ).strip()

    def _criteria_from_scores(self, scores):
        """
        WritingScore.criterion = enum WritingCriterion (value => 'task_achievement', ...)
        WritingScore.score = float
        """
        m = {}
        for s in scores or []:
            crit = getattr(s, "criterion", None)
            key = None
            if crit is not None:
                key = getattr(crit, "value", None) or str(crit)
            val = getattr(s, "score", None)
            if key:
                m[str(key)] = val
        return m

    def _task_title_and_ids(self, ans) -> str:
        task = getattr(ans, "task", None)
        task_id = getattr(ans, "task_id", None)

        if task:
            part = getattr(task, "part_number", None)
            sub = getattr(task, "sub_part", None)
            if part is not None and sub is not None:
                return f"Part {part}.{sub}  (Task ID: {task_id})"
            if part is not None:
                return f"Part {part}  (Task ID: {task_id})"

        return f"Task (Task ID: {task_id})" if task_id is not None else "Task"

    def _prompt_block_from_task(self, ans) -> str:
        task = getattr(ans, "task", None)
        if not task:
            return "Task not loaded. (Missing selectinload(WritingAnswer.task))"

        topic = (getattr(task, "topic", None) or "").strip()
        context = (getattr(task, "context_text", None) or "").strip()
        instruction = (getattr(task, "instruction", None) or "").strip()

        parts = []
        if topic:
            parts.append(f"TOPIC:\n{topic}")
        if context:
            parts.append(f"CONTEXT:\n{context}")
        if instruction:
            parts.append(f"INSTRUCTION:\n{instruction}")

        return "\n\n".join(parts) if parts else "Prompt not found."

    def _pick_feedback(self, ans) -> str:
        feedbacks = getattr(ans, "feedbacks", None) or []
        if not feedbacks:
            return "No feedback."

        # oxirgisi (odatda eng yangi)
        fb = feedbacks[-1]
        return (getattr(fb, "content", None) or "No feedback.").strip()

    # -------------------------------------------------------
    # MAIN
    # -------------------------------------------------------
    async def generate_pdf_report(self, result):
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=30 * mm,
            bottomMargin=22 * mm,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Heading1"],
            fontSize=18,
            alignment=1,
            spaceAfter=10,
        )

        section_style = ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontSize=13,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=10,
            spaceAfter=6,
        )

        label_style = ParagraphStyle(
            "Label",
            parent=styles["Normal"],
            fontSize=9.5,
            textColor=colors.HexColor("#475569"),
            leading=12,
        )

        normal_style = ParagraphStyle(
            "Normal2",
            parent=styles["Normal"],
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#0f172a"),
        )

        elements = []

        # -------------------------
        # SUMMARY PAGE
        # -------------------------
        report_id = f"ENWIS-{uuid.uuid4().hex[:8].upper()}"

        result_id = getattr(result, "id", None)
        user_id = getattr(result, "user_id", None)
        exam_id = getattr(result, "exam_id", None)

        user_name = self._get_user_name(result)
        exam_title = self._get_exam_title(result)

        created_at = self._fmt_dt(getattr(result, "created_at", None))
        is_finalized = getattr(result, "is_finalized", None)

        raw_score = getattr(result, "raw_score", None)
        scaled_score = getattr(result, "scaled_score", None)

        cefr_level = getattr(result, "cefr_level", None)
        cefr_level_val = getattr(cefr_level, "value", None) or (str(cefr_level) if cefr_level else None)

        elements.append(Paragraph("WRITING EXAM REPORT", title_style))
        elements.append(HRFlowable(width="100%", thickness=1.0, color=colors.HexColor("#e2e8f0")))
        elements.append(Spacer(1, 6 * mm))

        rows = []
        if result_id is not None:
            rows.append(["Result ID:", str(result_id)])
        if user_id is not None:
            rows.append(["User ID:", str(user_id)])

        rows.append(["Candidate Name:", user_name])

        if exam_id is not None:
            rows.append(["Exam ID:", str(exam_id)])
        rows.append(["Exam Title:", exam_title])

        rows.append(["Created At:", created_at])
        rows.append(["Report ID:", report_id])

        if cefr_level_val is not None:
            rows.append(["CEFR Level:", str(cefr_level_val)])
        if raw_score is not None:
            rows.append(["Raw Score:", str(raw_score)])
        if scaled_score is not None:
            rows.append(["Scaled Score:", str(scaled_score)])
        if is_finalized is not None:
            rows.append(["Finalized:", "YES" if bool(is_finalized) else "NO"])

        table = Table(rows, colWidths=[45 * mm, 120 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(table)
        elements.append(PageBreak())

        # -------------------------
        # TASK PAGES
        # -------------------------
        answers = getattr(result, "answers", None) or []
        try:
            answers = sorted(answers, key=lambda a: getattr(a, "task_id", 0) or 0)
        except Exception:
            pass

        # ✅ bo‘sh bo‘lib qolmasin:
        if not answers:
            elements.append(Paragraph("No answers found for this result.", section_style))
            elements.append(Spacer(1, 4 * mm))
            elements.append(Paragraph(
                "Possible reason: result was loaded without answers/task/scores/feedbacks. "
                "Fix: selectinload(WritingResult.answers).selectinload(WritingAnswer.task) ...",
                normal_style
            ))
        else:
            for idx, ans in enumerate(answers, start=1):
                title = self._task_title_and_ids(ans)
                prompt_text = self._prompt_block_from_task(ans)
                feedback_text = self._pick_feedback(ans)

                elements.append(Paragraph(title, section_style))
                elements.append(Spacer(1, 2 * mm))

                elements.append(Paragraph("<b>Task Prompt:</b>", label_style))
                elements.append(self._safe_paragraph(prompt_text, normal_style))
                elements.append(Spacer(1, 5 * mm))

                elements.append(Paragraph("<b>Student Response:</b>", label_style))
                elements.append(self._safe_paragraph(getattr(ans, "content", "") or "", normal_style))
                elements.append(Spacer(1, 5 * mm))

                wc = getattr(ans, "word_count", None)
                pen = getattr(ans, "penalty", None)
                a_raw = getattr(ans, "raw_score", None)
                a_scaled = getattr(ans, "scaled_score", None)

                meta = []
                if wc is not None:
                    meta.append(f"Words: {wc}")
                if pen is not None:
                    meta.append(f"Penalty: {pen}")
                if a_raw is not None:
                    meta.append(f"Answer Raw: {a_raw}")
                if a_scaled is not None:
                    meta.append(f"Answer Scaled: {a_scaled}")

                if meta:
                    elements.append(Paragraph(" • ".join(meta), label_style))
                    elements.append(Spacer(1, 4 * mm))

                score_map = self._criteria_from_scores(getattr(ans, "scores", None) or [])

                # ✅ criteria ro‘yxati: sening enumlaringga mos
                criteria_rows = [
                    ["Task Achievement", score_map.get("task_achievement", 0)],
                    ["Coherence", score_map.get("coherence", 0)],
                    ["Vocabulary", score_map.get("vocabulary", 0)],
                    ["Grammar", score_map.get("grammar", 0)],
                    ["Mechanics", score_map.get("mechanics", 0)],
                    ["Overall", score_map.get("overall", 0)],
                ]

                criteria_table = Table(criteria_rows, colWidths=[95 * mm, 25 * mm])
                criteria_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]))
                elements.append(criteria_table)
                elements.append(Spacer(1, 5 * mm))

                elements.append(Paragraph("<b>AI Feedback:</b>", label_style))
                elements.append(self._safe_paragraph(feedback_text, normal_style))

                if idx != len(answers):
                    elements.append(PageBreak())

        # -------------------------
        # BUILD
        # -------------------------
        doc.build(
            elements,
            onFirstPage=lambda c, d: self._draw_header_footer(c, d, user_name),
            onLaterPages=lambda c, d: self._draw_header_footer(c, d, user_name),
        )

        return buffer.getvalue()