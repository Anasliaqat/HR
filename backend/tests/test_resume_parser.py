from pathlib import Path

from docx import Document

from app.services.resume_parser import extract_profile, extract_text


def test_docx_sections_and_skill_table_are_extracted_into_their_sections(
    tmp_path: Path,
) -> None:
    document = Document()
    document.add_paragraph("PROFESSIONAL SUMMARY")
    document.add_paragraph("Junior developer familiar with Python and GenAI.")
    document.add_paragraph("TECHNICAL SKILLS")
    document.add_paragraph("EDUCATION")
    document.add_paragraph("Bachelor's in Information Technology")
    document.add_paragraph("TRAINING")
    document.add_paragraph("AI and Machine Learning Training")
    document.add_paragraph("PROJECT EXPERIENCE")
    document.add_paragraph("Building an AI assistant with RAG.")
    document.add_paragraph("CORE STRENGTHS")
    document.add_paragraph("Problem solving, collaboration")
    document.add_paragraph("CAREER OBJECTIVE")
    document.add_paragraph("Seeking a junior AI/ML developer role.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "AI / ML"
    table.cell(0, 1).text = "TensorFlow, NumPy, Pandas"
    table.cell(1, 0).text = "Tools"
    table.cell(1, 1).text = "Git, GitHub, GitHub Copilot"
    path = tmp_path / "sectioned-cv.docx"
    document.save(path)

    extracted_text = extract_text(path)
    profile = extract_profile(extracted_text)

    assert "TensorFlow, NumPy, Pandas" in extracted_text
    assert any("Python" in line for line in profile.summary)
    assert "TensorFlow" in profile.skills
    assert "Pandas" in profile.skills
    assert "GitHub Copilot" in profile.skills
    assert profile.education == ["Bachelor's in Information Technology"]
    assert profile.certifications == ["AI and Machine Learning Training"]
    assert any("AI assistant with RAG" in line for line in profile.projects)
    assert "Problem solving" in profile.skills[0]
